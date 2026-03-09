import os
from datetime import datetime, timedelta
from functools import partial
from json import JSONDecodeError
from logging import Logger
from typing import Any, Callable

import requests
from litestar.status_codes import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
from requests import Session, HTTPError, Response

from common import SharlyChessException
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.event import Event
from data.loader import EventLoader
from data.player_categories import PlayerCategory
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredTournament,
    StoredPlayer,
    StoredTournamentPlayer,
)
from plugins import ffe
from plugins.ffe.utils import FfePlayerPluginData, PlayerFFELicence
from plugins.manager import plugin_manager
from plugins.sce import PLUGIN_NAME
from plugins.sce.utils import (
    SCETokens,
    SCEUtils,
    SCETournamentPluginData,
    SCEPlayerPluginData,
)
from plugins.utils import Plugin
from utils import Utils
from utils.enum import TournamentRating, PlayerRatingType, PlayerTitle
from utils.types import PlayerRating
from web.urls import build_get_url

logger: Logger = get_logger()

SCE_BASE_URL = os.getenv('SCE_BASE_URL') or 'http://localhost:3001'
CLIENT_ID = 'sharlychess'

# Only one token is handled at a time per event
# These scopes should therefore provide for all the app's features
REQUIRED_SCOPES = [
    'event:read',
    'tournaments:read',
    'registrations:read',
    'registrations:write',
]


class SCESession(Session):
    """A requests session specialized for communication with SCE.com."""

    def __init__(self, event: Event):
        super().__init__()
        self.event = event

    @property
    def tokens(self) -> SCETokens:
        tokens = SCEUtils.get_event_plugin_data(self.event).tokens
        assert tokens is not None
        return tokens

    @property
    def sce_event_id(self) -> str:
        event_id = SCEUtils.get_event_plugin_data(self.event).id
        assert event_id is not None
        return event_id

    @property
    def api_headers(self) -> dict[str, str]:
        return {
            'Authorization': f'Bearer {self.tokens.access_token}',
            'Content-Type': 'application/json',
        }

    @property
    def base_event_url(self) -> str:
        return SCE_BASE_URL + '/api/v1/events/' + self.sce_event_id

    def _update_event_tokens(self, tokens: SCETokens | None):
        plugin_data = SCEUtils.get_event_plugin_data(self.event)
        plugin_data.tokens = tokens
        self.event.plugin_data[PLUGIN_NAME] = plugin_data
        stored_event = self.event.stored_event
        stored_event.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
        with EventDatabase(self.event.uniq_id, True) as database:
            database.update_stored_event(stored_event)

    @classmethod
    def build_oauth_url(
        cls,
        redirect_uri: str,
        state: str,
        code_challenge: str,
        code_challenge_method: str = 'S256',
        response_type: str = 'code',
        event_id: str | None = None,
    ) -> str:
        params: dict[str, Any] = {
            'client_id': CLIENT_ID,
            'redirect_uri': redirect_uri,
            'scope': ' '.join(REQUIRED_SCOPES),
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': code_challenge_method,
            'response_type': response_type,
        }
        if event_id:
            params['event_id'] = event_id
        return build_get_url(SCE_BASE_URL, '/api/oauth/authorize', params)

    @staticmethod
    def validate_api_response(response: Response):
        """Validate a response, raising a SharlyChessException if invalid and logging the error."""
        request_log = f'{response.request.method} {response.url} {response.status_code}'
        try:
            response.raise_for_status()
            logger.debug(request_log)
        except HTTPError as e:
            try:
                logger.error(response.json())
            except JSONDecodeError:
                pass
            raise SharlyChessException(str(e))

    @classmethod
    def get_tokens_from_code(
        cls, code: str, code_verifier: str, redirect_uri: str
    ) -> SCETokens:
        response = requests.post(
            SCE_BASE_URL + '/api/oauth/token',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'grant_type': 'authorization_code',
                'code': code,
                'code_verifier': code_verifier,
                'client_id': CLIENT_ID,
                'redirect_uri': redirect_uri,
            },
        )
        cls.validate_api_response(response)
        data = response.json()
        return SCETokens(
            access_token=data['access_token'],
            refresh_token=data['refresh_token'],
            expires_at=datetime.now() + timedelta(seconds=data['expires_in']),
        )

    def refresh_tokens(self):
        response = requests.post(
            SCE_BASE_URL + '/api/oauth/token',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'grant_type': 'refresh_token',
                'refresh_token': self.tokens.refresh_token,
                'client_id': CLIENT_ID,
            },
        )
        if response.status_code in [HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN]:
            # Refresh token no longer valid, needs to be regenerated via OAuth
            self._update_event_tokens(None)
        self.validate_api_response(response)
        data = response.json()
        tokens = SCETokens(
            access_token=data['access_token'],
            refresh_token=data['refresh_token'],
            expires_at=datetime.now() + timedelta(seconds=data['expires_in']),
        )
        self._update_event_tokens(tokens)

    def _run_with_token_validation(
        self,
        request_function: Callable[[], Response],
        skip_validation: bool = False,
    ) -> Response:
        """Wrapper on a request function which regenerates the token if they are outdated."""
        if self.tokens.expires_at < datetime.now():
            self.refresh_tokens()
        response = request_function()
        if response.status_code in [HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN]:
            self.refresh_tokens()
            response = request_function()
        if not skip_validation:
            self.validate_api_response(response)
        return response

    def _get_event_request(self) -> Response:
        return requests.get(self.base_event_url, headers=self.api_headers)

    def _get_tournament_reservations_request(self, sce_tournament_id: str) -> Response:
        return requests.get(
            self.base_event_url + f'/tournaments/{sce_tournament_id}/registrations',
            headers=self.api_headers,
        )

    def _create_tournament(self, data: dict[str, Any], database: EventDatabase):
        sce_tournament_id = data['id']
        start_date = datetime.fromisoformat(data['start_date']).date()
        stop_date = datetime.fromisoformat(data['end_date']).date()
        defaut_dates = (
            start_date == self.event.start_date and stop_date == self.event.stop_date
        )
        stored_tournament = StoredTournament(
            id=None,
            name=data['name'],
            rating=TournamentRating.from_key(data['type']).value,
            start_date=None if defaut_dates else start_date,
            stop_date=None if defaut_dates else stop_date,
            plugin_data={
                PLUGIN_NAME: SCETournamentPluginData(
                    sce_tournament_id
                ).to_stored_value()
            },
        )
        stored_tournament.id = database.add_stored_tournament(stored_tournament)
        tournament = Tournament(self.event, stored_tournament)
        response = self._run_with_token_validation(
            partial(self._get_tournament_reservations_request, sce_tournament_id)
        )
        for registration_data in response.json()['data']:
            self._create_player_from_registration_data(
                registration_data, tournament, database
            )

    def _create_player_from_registration_data(
        self,
        data: dict[str, Any],
        tournament: Tournament,
        database: EventDatabase,
    ):
        plugin_data = {
            PLUGIN_NAME: SCEPlayerPluginData(data['id']).to_stored_value(),
        }
        if self.event.federation == 'FRA':
            plugin_data[ffe.PLUGIN_NAME] = FfePlayerPluginData(
                ffe_licence_number=data['national_id'],
                ffe_id=None,
                ffe_licence=PlayerFFELicence.NONE,
                league=None,
            ).to_stored_value()
        stored_player = StoredPlayer(
            id=None,
            first_name=data['first_name'],
            last_name=data['last_name'],
            federation=self.event.federation,
            year_of_birth=data['year_of_birth'],
            fide_id=data['fide_id'],
            title=PlayerTitle(data['title'] or '').value,
            club=data['club'],
            ratings={
                tournament.rating.value: PlayerRating.from_type(
                    data['rating'],
                    PlayerRatingType.from_key(data['rating_type'] or 'E'),
                ).stored_value
            },
            plugin_data=plugin_data,
        )
        stored_player.id = database.add_stored_player(stored_player)
        database.add_stored_tournament_player(
            StoredTournamentPlayer(
                player_id=stored_player.id,
                tournament_id=tournament.id,
            )
        )

    def update_event_from_sce_event(self, is_create: bool = False):
        from plugins.ffe.ffe import FfePlugin
        from plugins.sce.sce import SCEPlugin

        response = self._run_with_token_validation(self._get_event_request)
        data = response.json()['data']

        stored_event = self.event.stored_event
        if is_create:
            stored_event.name = EventLoader().get_unused_event_name(data['name'])
            stored_event.federation = (
                Utils.get_federation_from_alpha_2_country_code(data['country']) or 'FID'
            )
            plugins: list[Plugin] = [SCEPlugin()]
            if stored_event.federation == 'FRA':
                plugins.append(FfePlugin())
            stored_event.enabled_plugins = [
                plugin.id
                for plugin in plugin_manager.get_plugins_with_dependencies(plugins)
            ]
            stored_event.timer_delays = SharlyChessConfig.default_timer_delays  # type: ignore
            stored_event.timer_colors = SharlyChessConfig.default_timer_colors  # type: ignore

        stored_event.start_date = datetime.fromisoformat(data['start_date']).date()
        stored_event.stop_date = datetime.fromisoformat(data['end_date']).date()
        stored_event.location = data['city']
        age_categories = [
            PlayerCategory.from_id(
                f'O{sce_category[:-1]}' if sce_category.endswith('+') else sce_category
            )
            for sce_category in data['age_categories']
        ]
        stored_event.age_categories = [
            category.id for category in sorted(age_categories)
        ]
        stored_event.age_category_base_date = (
            datetime.fromisoformat(data['age_category_base_date']).date()
            if data['age_category_base_date']
            else None
        )
        stored_event.age_category_change_month = data['age_category_change_month']
        stored_event.prize_currency = data['currency']
        with EventDatabase(stored_event.uniq_id, True) as database:
            database.update_stored_event(stored_event)
            if is_create:
                for tournament_data in data['tournaments']:
                    self._create_tournament(tournament_data, database)
        new_uniq_id = EventLoader().get_unused_event_uniq_id(data['slug'])
        EventDatabase(self.event.uniq_id).rename(new_uniq_id)
        stored_event.uniq_id = new_uniq_id
