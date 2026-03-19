import os
from datetime import datetime, timedelta
from functools import partial
from json import JSONDecodeError
from logging import Logger
from typing import Any, Callable

import requests
from litestar.status_codes import (
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_200_OK,
    HTTP_404_NOT_FOUND,
)
from requests import Session, HTTPError, Response

from common import SharlyChessException
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.event import Event
from data.loader import EventLoader
from data.player import TournamentPlayer
from data.player_categories import PlayerCategory
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredTournament,
    StoredPlayer,
    StoredTournamentPlayer,
)
from plugins.manager import plugin_manager
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_event_status import (
    NotFoundSCEEventStatus,
    UnexpectedHttpSCEEventStatus,
    NotReachableSCEEventStatus,
)
from plugins.sce.utils import (
    SCETokens,
    SCEUtils,
    SCETournamentPluginData,
    SCEPlayerPluginData,
    SCEEventPluginData,
    SCEPlayerSyncData,
    SCETournamentSyncData,
)
from plugins.utils import Plugin
from utils import Utils
from utils.enum import Result
from web.urls import build_get_url

logger: Logger = get_logger()

SCE_BASE_URL = os.getenv('SCE_BASE_URL') or 'http://localhost:3001'
SCE_SYNC_DELAY = 3
SCE_UPLOAD_DELAY = 3
CLIENT_ID = 'sharlychess'

# Only one token is handled at a time per event
# These scopes should therefore provide for all the app's features
REQUIRED_SCOPES = [
    'event:read',
    'tournaments:read',
    'tournaments:write',
    'registrations:read',
    'registrations:write',
]


class SCESession(Session):
    """A requests session specialized for communication with Sharly-Chess.com."""

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

    def tournament_url(self, tournament_id: str) -> str:
        return self.base_event_url + '/tournaments/' + tournament_id

    def registration_url(self, tournament_id: str, registration_id: str) -> str:
        return self.tournament_url(tournament_id) + '/registrations/' + registration_id

    def _log_sync_operation(self, message: str, is_info: bool = False):
        full_message = (
            f'Sharly-Chess.com sync - Event [{self.event.uniq_id}] - {message}'
        )
        if is_info:
            logger.info(full_message)
        else:
            logger.debug(full_message)

    # -------------------------------------------------------------------------
    # Auth
    # -------------------------------------------------------------------------

    def _update_event_tokens(self, tokens: SCETokens | None):
        plugin_data = SCEUtils.get_event_plugin_data(self.event)
        plugin_data.tokens = tokens
        SCEUtils.update_event_plugin_data(self.event, plugin_data)

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
            logger.error(request_log)
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
        if not SCEUtils.get_event_plugin_data(self.event).tokens:
            raise SharlyChessException(
                f'Event [{self.event.uniq_id}] - Sharly-Chess.com tokens not set'
            )
        try:
            if self.tokens.expires_at < datetime.now():
                self.refresh_tokens()
            response = request_function()
            if response.status_code in [HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN]:
                self.refresh_tokens()
                response = request_function()
            if not skip_validation:
                self.validate_api_response(response)
        except requests.ConnectionError as e:
            plugin_data = SCEUtils.get_event_plugin_data(self.event)
            plugin_data.status = NotReachableSCEEventStatus().id
            SCEUtils.update_event_plugin_data(self.event, plugin_data)
            raise SharlyChessException(str(e))
        return response

    # -------------------------------------------------------------------------
    # Player
    # -------------------------------------------------------------------------

    def _create_registration_request(
        self,
        data: SCEPlayerSyncData,
    ):
        payload = data.to_sce_data()
        return requests.post(
            self.tournament_url(data.tournament_id) + '/registrations',
            headers=self.api_headers,
            json=payload,
        )

    def create_sce_player(self, data: SCEPlayerSyncData) -> str:
        response = self._run_with_token_validation(
            partial(self._create_registration_request, data=data)
        )
        return response.json()['data']['id']

    def _update_registration_request(
        self,
        data: SCEPlayerSyncData,
        sce_tournament_id: str,
        sce_player_id: str,
        set_canceled_status: bool = False,
    ):
        payload = data.to_sce_data()
        if set_canceled_status:
            payload['status'] = 'cancelled'
        return requests.patch(
            self.registration_url(sce_tournament_id, sce_player_id),
            headers=self.api_headers,
            json=payload,
        )

    def update_sce_player(
        self,
        data: SCEPlayerSyncData,
        sce_tournament_id: str,
        sce_player_id: str,
        set_canceled_status: bool = False,
    ):
        self._run_with_token_validation(
            partial(
                self._update_registration_request,
                data=data,
                sce_tournament_id=sce_tournament_id,
                sce_player_id=sce_player_id,
                set_canceled_status=set_canceled_status,
            )
        )

    def _delete_registration_request(self, sce_tournament_id: str, sce_player_id: str):
        return requests.delete(
            self.registration_url(sce_tournament_id, sce_player_id),
            headers=self.api_headers,
        )

    def delete_sce_player(
        self,
        sce_tournament_id: str,
        sce_player_id: str,
    ):
        self._run_with_token_validation(
            partial(
                self._delete_registration_request,
                sce_tournament_id=sce_tournament_id,
                sce_player_id=sce_player_id,
            )
        )

    def _create_local_player(
        self,
        sce_id: str,
        sync_data: SCEPlayerSyncData,
        tournament: Tournament,
        database: EventDatabase,
    ):
        sce_tournament_id = SCEUtils.get_tournament_plugin_data(tournament).id
        assert sce_tournament_id is not None
        stored_player = StoredPlayer(
            id=None,
            federation=self.event.federation,
            plugin_data={
                PLUGIN_NAME: SCEPlayerPluginData(id=sce_id).to_stored_value(),
            },
        )
        sync_data.augment_stored_player(stored_player, tournament)
        stored_player.id = database.add_stored_player(stored_player)
        database.add_stored_tournament_player(
            StoredTournamentPlayer(
                player_id=stored_player.id,
                tournament_id=tournament.id,
            )
        )

    def update_local_player(self, player: TournamentPlayer, data: SCEPlayerSyncData):
        data.augment_stored_player(
            player.stored_player,
            player.tournament,
            player.rating,
            player.rating_type,
        )
        sce_tournament_id = SCEUtils.get_tournament_plugin_data(player.tournament).id
        if sce_tournament_id != data.tournament_id:
            # Player changed tournament
            new_tournament = SCEUtils.get_tournament_by_sce_id(
                self.event, data.tournament_id
            )
            self.event.move_player_to_tournament(player, new_tournament)

    def _sync_player(
        self, player: TournamentPlayer, sce_sync_data: SCEPlayerSyncData | None
    ) -> bool:
        def log_operation(message: str):
            log_name = player.last_name
            if player.first_name:
                log_name += f' {player.first_name}'
            self._log_sync_operation(f'Player [{log_name}] - {message}')

        plugin_data = SCEUtils.get_player_plugin_data(player)
        sce_id = plugin_data.id
        if not sce_id:
            if not plugin_data.deleted_id:
                sync_data = SCEPlayerSyncData.from_player(player)
                plugin_data.id = self.create_sce_player(sync_data)
                plugin_data.last_sync_data = sync_data
                SCEUtils.update_player_plugin_data(player, plugin_data)
                log_operation('Creation (SC.com)')
            return True
        tournament = player.tournament
        if not sce_sync_data:
            if player.has_real_pairings:
                # Soft delete
                plugin_data.deleted_id = sce_id
                plugin_data.id = None
                SCEUtils.update_player_plugin_data(player, plugin_data)
                new_byes = {
                    round_: Result.ZERO_POINT_BYE
                    for round_ in range(
                        tournament.current_round or 1,
                        tournament.rounds + 1,
                    )
                    if player.pairings[round_].unpaired
                }
                tournament.set_player_byes(player.single_tournament_player, new_byes)
                log_operation('Soft-deletion (local)')
            else:
                with EventDatabase(self.event.uniq_id, True) as database:
                    database.delete_stored_player(player.id)
                    log_operation('Deletion (local)')
            return True

        has_conflict = False

        local_sync_data = SCEPlayerSyncData.from_player(player)
        if (
            local_sync_data.tournament_id != sce_sync_data.tournament_id
            and player.has_real_pairings
        ):
            # Paired player + different tournaments --> Force to local tournament
            sce_tournament_id = sce_sync_data.tournament_id
            sce_sync_data.tournament_id = local_sync_data.tournament_id
            self.update_sce_player(sce_sync_data, sce_tournament_id, sce_id)
            log_operation(
                f'Tournament forced to [{local_sync_data.tournament_id}] (SC.com)'
            )

        # reset has_order to not take it into account in data comparison
        sce_sync_data.has_order = None
        if local_sync_data == sce_sync_data:
            # Already synced
            plugin_data.last_sync_data = local_sync_data
        elif sce_sync_data == plugin_data.last_sync_data:
            # Modified locally --> update SC.com value
            self.update_sce_player(local_sync_data, sce_sync_data.tournament_id, sce_id)
            plugin_data.last_sync_data = local_sync_data
            log_operation('Local changes uploaded (SC.com)')
        elif local_sync_data == plugin_data.last_sync_data:
            # Modified on SC.com --> update locally
            self.update_local_player(player, sce_sync_data)
            plugin_data.last_sync_data = sce_sync_data
            log_operation('SC.com changes imported (local)')
        else:
            # Modified on both ends
            try:
                assert plugin_data.last_sync_data is not None
                merged_sync_data = local_sync_data.merge_with_other_sync_data(
                    sce_sync_data, plugin_data.last_sync_data
                )
                # Mergeable --> Update locally and on SC.com
                self.update_sce_player(
                    merged_sync_data, sce_sync_data.tournament_id, sce_id
                )
                self.update_local_player(player, merged_sync_data)
                plugin_data.last_sync_data = merged_sync_data
                log_operation('Dual changes merged (SC.com + local)')
            except SharlyChessException as e:
                # Not mergeable --> Create a conflict
                plugin_data.conflict_sync_data = sce_sync_data
                has_conflict = True
                log_operation(
                    f'Not mergeable dual changes, conflict created (details: {e})'
                )
        SCEUtils.update_player_plugin_data(player, plugin_data)
        return not has_conflict

    # -------------------------------------------------------------------------
    # Tournament
    # -------------------------------------------------------------------------

    def import_tournaments(self, sce_tournament_ids: list[str]):
        data = self._get_event_data(with_active_registrations=True)
        with EventDatabase(self.event.uniq_id, True) as database:
            for tournament_data in data['tournaments']:
                if tournament_data['id'] in sce_tournament_ids:
                    self._create_local_tournament(tournament_data, database)

    def _create_local_tournament(
        self, raw_data: dict[str, Any], database: EventDatabase
    ):
        sce_id = raw_data['id']
        stored_tournament = StoredTournament(
            id=None,
            name='',
            index=(
                max(tournament.index for tournament in self.event.tournaments) + 1
                if self.event.tournaments
                else 0
            ),
            plugin_data={
                PLUGIN_NAME: SCETournamentPluginData(id=sce_id).to_stored_value()
            },
        )
        sync_data = SCETournamentSyncData.from_sce_data(raw_data)
        sync_data.augment_stored_tournament(stored_tournament, self.event)
        stored_tournament.id = database.add_stored_tournament(stored_tournament)
        tournament = Tournament(self.event, stored_tournament)
        for registration_data in raw_data['registrations']:
            self._create_local_player(
                registration_data['id'],
                SCEPlayerSyncData.from_sce_data(registration_data, sce_id),
                tournament,
                database,
            )

    def _update_tournament_request(
        self, data: SCETournamentSyncData, sce_tournament_id: str
    ):
        return requests.patch(
            self.tournament_url(sce_tournament_id),
            headers=self.api_headers,
            json=data.to_sce_data(),
        )

    def update_sce_tournament(
        self, data: SCETournamentSyncData, sce_tournament_id: str
    ):
        self._run_with_token_validation(
            partial(
                self._update_tournament_request,
                data=data,
                sce_tournament_id=sce_tournament_id,
            )
        )

    def resolve_tournament_conflict(self, tournament: Tournament, accept_local: bool):
        plugin_data = SCEUtils.get_tournament_plugin_data(tournament)
        if not plugin_data.id or not plugin_data.conflict_sync_data:
            return
        if accept_local:
            local_sync_data = SCETournamentSyncData.from_tournament(tournament)
            self.update_sce_tournament(local_sync_data, plugin_data.id)
            plugin_data.conflict_sync_data = local_sync_data
        else:
            plugin_data.conflict_sync_data.augment_stored_tournament(
                tournament.stored_tournament, self.event
            )
            plugin_data.last_sync_data = plugin_data.conflict_sync_data
        SCEUtils.update_tournament_plugin_data(tournament, plugin_data)

    def _sync_tournament(
        self, tournament: Tournament, tournament_data_by_id: dict[str, dict[str, Any]]
    ):
        """Synchronize a tournament with its SC.com equivalent.
        Returns a status boolean indicating False if it has conflicts."""

        def log_operation(message: str):
            self._log_sync_operation(f'Tournament [{tournament.name}] - {message}')

        plugin_data = SCEUtils.get_tournament_plugin_data(tournament)
        sce_tournament_id = plugin_data.id
        if not sce_tournament_id:
            return True
        plugin_data.conflict_sync_data = None
        if plugin_data.id not in tournament_data_by_id:
            plugin_data.id = None
            SCEUtils.update_tournament_plugin_data(tournament, plugin_data)
            log_operation('SC.com tournament was deleted, connection removed (local)')
            return True
        has_conflicts = False
        sce_sync_data = SCETournamentSyncData.from_sce_data(
            tournament_data_by_id[sce_tournament_id]
        )
        local_sync_data = SCETournamentSyncData.from_tournament(tournament)
        if local_sync_data == sce_sync_data:
            # Already synced
            plugin_data.last_sync_data = local_sync_data
        elif sce_sync_data == plugin_data.last_sync_data:
            # Modified locally --> update SC.com value
            self.update_sce_tournament(local_sync_data, sce_tournament_id)
            plugin_data.last_sync_data = local_sync_data
            log_operation('Local changes uploaded (SC.com)')
        elif local_sync_data == plugin_data.last_sync_data:
            # Modified on SC.com --> update locally
            plugin_data.last_sync_data = sce_sync_data
            sce_sync_data.augment_stored_tournament(
                tournament.stored_tournament, self.event
            )
            log_operation('SC.com changes imported (local)')
        else:
            # Modified on both ends
            try:
                assert plugin_data.last_sync_data is not None
                merged_sync_data = local_sync_data.merge_with_other_sync_data(
                    sce_sync_data, plugin_data.last_sync_data
                )
                # Mergeable --> Update locally and on SC.com
                self.update_sce_tournament(merged_sync_data, sce_tournament_id)
                merged_sync_data.augment_stored_tournament(
                    tournament.stored_tournament, self.event
                )
                plugin_data.last_sync_data = merged_sync_data
                log_operation('Dual changes merged (SC.com + local)')
            except SharlyChessException as e:
                # Not mergeable --> Create a conflict
                logger.debug(e)
                plugin_data.conflict_sync_data = sce_sync_data
                has_conflicts = True
                log_operation(
                    f'Not mergeable dual changes, conflict created (details: {e})'
                )
        SCEUtils.update_tournament_plugin_data(tournament, plugin_data)
        return not has_conflicts

    # -------------------------------------------------------------------------
    # Event
    # -------------------------------------------------------------------------

    def _get_event_request(self, with_active_registrations: bool = False) -> Response:
        params = {}
        if with_active_registrations:
            params['with_active_registrations'] = 'true'
        return requests.get(
            build_get_url(SCE_BASE_URL, '/api/v1/events/' + self.sce_event_id, params),
            headers=self.api_headers,
        )

    def _get_event_data(
        self, with_active_registrations: bool = False
    ) -> dict[str, Any]:
        response = self._run_with_token_validation(
            partial(
                self._get_event_request,
                with_active_registrations=with_active_registrations,
            ),
            skip_validation=True,
        )
        if response.status_code != HTTP_200_OK:
            stored_event = self.event.stored_event
            plugin_data = SCEEventPluginData.from_stored_value(
                stored_event.plugin_data.get(PLUGIN_NAME, {})
            )
            plugin_data.status = (
                NotFoundSCEEventStatus.static_id()
                if response.status_code == HTTP_404_NOT_FOUND
                else UnexpectedHttpSCEEventStatus.static_id()
            )
            SCEUtils.update_event_plugin_data(self.event, plugin_data)
            self.validate_api_response(response)
        return response.json()['data']

    def update_event_from_sce_event(
        self,
        is_create: bool = False,
        update_tournament_conflicts: bool = False,
        update_player_conflicts: bool = False,
    ):
        from plugins.ffe.ffe import FfePlugin
        from plugins.sce.sce import SCEPlugin

        data = self._get_event_data(
            with_active_registrations=is_create or update_player_conflicts
        )
        stored_event = self.event.stored_event
        plugin_data = SCEEventPluginData.from_stored_value(
            stored_event.plugin_data.get(PLUGIN_NAME, {})
        )
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
            stored_event.organiser_name = data['organizer']['name']
            stored_event.prize_currency = data['currency']
            stored_event.location = data['city']
            stored_event.timer_delays = SharlyChessConfig.default_timer_delays  # type: ignore
            stored_event.timer_colors = SharlyChessConfig.default_timer_colors  # type: ignore

        plugin_data.slug = data['slug']
        plugin_data.organiser_slug = data['organizer']['slug']
        plugin_data.status = data['status']
        plugin_data.tournament_names_by_id = {
            tournament_data['id']: tournament_data['name']
            for tournament_data in data['tournaments']
        }
        SCEUtils.update_event_plugin_data(self.event, plugin_data, write=False)

        if (
            not stored_event.organiser_home_page
            or not stored_event.organiser_home_page.startswith(SCE_BASE_URL)
        ):
            stored_event.organiser_home_page = build_get_url(
                SCE_BASE_URL, f'/o/{plugin_data.organiser_slug}'
            )
        stored_event.start_date = datetime.fromisoformat(data['start_date']).date()
        stored_event.stop_date = datetime.fromisoformat(data['end_date']).date()
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
        with EventDatabase(stored_event.uniq_id, True) as database:
            database.update_stored_event(stored_event)
            if is_create:
                for tournament_data in data['tournaments']:
                    self._create_local_tournament(tournament_data, database)
        if is_create:
            new_uniq_id = EventLoader().get_unused_event_uniq_id(data['slug'])
            EventDatabase(self.event.uniq_id).rename(new_uniq_id)
            stored_event.uniq_id = new_uniq_id
        elif update_tournament_conflicts or update_player_conflicts:
            tournament_data_by_id = {
                tournament_data['id']: tournament_data
                for tournament_data in data['tournaments']
            }
            self._update_conflicts(
                tournament_data_by_id,
                update_tournament_conflicts,
                update_player_conflicts,
            )

    def _update_conflicts(
        self,
        tournament_data_by_id: dict[str, dict[str, Any]],
        update_tournament_conflicts: bool,
        update_player_conflicts: bool,
    ):
        sce_player_sync_data_by_id: dict[str, SCEPlayerSyncData] = {}
        if update_player_conflicts:
            sce_tournament_ids = {
                SCEUtils.get_tournament_plugin_data(tournament).id
                for tournament in self.event.tournaments
            }
            for sce_tournament_id, tournament_data in tournament_data_by_id.items():
                if sce_tournament_id not in sce_tournament_ids:
                    continue
                for registration_data in tournament_data['registrations']:
                    sce_player_sync_data_by_id[registration_data['id']] = (
                        SCEPlayerSyncData.from_sce_data(
                            registration_data,
                            sce_tournament_id,
                            with_order_status=True,
                        )
                    )

        for tournament in self.event.tournaments:
            plugin_data = SCEUtils.get_tournament_plugin_data(tournament)
            if not plugin_data.id:
                continue
            if plugin_data.id not in tournament_data_by_id:
                plugin_data.id = None
                plugin_data.conflict_sync_data = None
                SCEUtils.update_tournament_plugin_data(tournament, plugin_data)
                continue
            if update_tournament_conflicts and plugin_data.conflict_sync_data:
                sce_sync_data = SCETournamentSyncData.from_sce_data(
                    tournament_data_by_id[plugin_data.id]
                )
                if sce_sync_data != plugin_data.conflict_sync_data:
                    plugin_data.conflict_sync_data = sce_sync_data
                    SCEUtils.update_tournament_plugin_data(tournament, plugin_data)
            if not update_player_conflicts:
                continue
            for player in tournament.tournament_players:
                player_plugin_data = SCEUtils.get_player_plugin_data(player)
                if (
                    not player_plugin_data.id
                    or not player_plugin_data.conflict_sync_data
                ):
                    continue
                sce_player_sync_data = sce_player_sync_data_by_id.get(
                    player_plugin_data.id
                )
                if (
                    sce_player_sync_data
                    and sce_player_sync_data != player_plugin_data.conflict_sync_data
                ):
                    player_plugin_data.conflict_sync_data = sce_player_sync_data
                    SCEUtils.update_player_plugin_data(player, player_plugin_data)

    def _log_player_data_operation(self, data: SCEPlayerSyncData, message: str):
        log_name = data.last_name
        if data.first_name:
            log_name += f' {data.first_name}'
        self._log_sync_operation(f'Player [{log_name}] - {message}')

    def sync_event(self) -> bool:
        """Synchronize the event with its SC.com equivalent.
        Returns False if there are conflicts to resolve.
        Raises a SharlyChessException if it fails."""
        self._log_sync_operation('Sync started', is_info=True)
        data = self._get_event_data(with_active_registrations=True)
        tournament_data_by_id = {
            tournament_data['id']: tournament_data
            for tournament_data in data['tournaments']
        }
        conflict_count = 0
        sce_tournaments = SCEUtils.get_event_sce_tournaments(self.event)
        for tournament in sce_tournaments:
            if not self._sync_tournament(tournament, tournament_data_by_id):
                conflict_count += 1
        if conflict_count:
            self._log_sync_operation(
                f'{conflict_count} tournament(s) have conflicts, player sync aborted',
                is_info=True,
            )
            return False

        sce_tournaments = SCEUtils.get_event_sce_tournaments(self.event)
        sce_tournament_ids = [
            SCEUtils.get_tournament_plugin_data(tournament).id
            for tournament in sce_tournaments
        ]
        sce_player_sync_data_by_id: dict[str, SCEPlayerSyncData] = {}
        for tournament_data in data['tournaments']:
            sce_id = tournament_data['id']
            if sce_id not in sce_tournament_ids:
                continue
            for registration_data in tournament_data['registrations']:
                sce_player_sync_data_by_id[registration_data['id']] = (
                    SCEPlayerSyncData.from_sce_data(
                        registration_data, sce_id, with_order_status=True
                    )
                )

        local_sce_player_ids: list[str] = []
        soft_deleted_players_by_id: dict[str, TournamentPlayer] = {}

        for tournament in sce_tournaments:
            for player in tournament.tournament_players:
                plugin_data = SCEUtils.get_player_plugin_data(player)
                if plugin_data.id:
                    local_sce_player_ids.append(plugin_data.id)
                elif plugin_data.deleted_id:
                    soft_deleted_players_by_id[plugin_data.deleted_id] = player

        event_plugin_data = SCEUtils.get_event_plugin_data(self.event)
        for sce_player_id, sce_sync_data in sce_player_sync_data_by_id.items():
            if sce_player_id in local_sce_player_ids:
                continue
            if sce_player_id in event_plugin_data.deleted_player_ids:
                sce_tournament_id = sce_sync_data.tournament_id
                if sce_sync_data.has_order:
                    self.update_sce_player(
                        sce_sync_data,
                        sce_tournament_id,
                        sce_player_id,
                        set_canceled_status=True,
                    )
                    self._log_player_data_operation(
                        sce_sync_data, 'Soft-deletion (SC.com)'
                    )
                else:
                    self.delete_sce_player(sce_tournament_id, sce_player_id)
                    self._log_player_data_operation(sce_sync_data, 'Deletion (SC.com)')
            else:
                # New player --> create locally
                tournament = SCEUtils.get_tournament_by_sce_id(
                    self.event, sce_sync_data.tournament_id
                )
                with EventDatabase(self.event.uniq_id, True) as database:
                    self._create_local_player(
                        sce_player_id, sce_sync_data, tournament, database
                    )
                self._log_player_data_operation(sce_sync_data, 'Creation (local)')

            if sce_player_id in soft_deleted_players_by_id:
                player = soft_deleted_players_by_id[sce_player_id]
                plugin_data = SCEUtils.get_player_plugin_data(player)
                plugin_data.id = plugin_data.deleted_id
                plugin_data.deleted_id = None
                SCEUtils.update_player_plugin_data(player, plugin_data)
                self._log_player_data_operation(
                    sce_sync_data, 'Restored after soft-deletion (local)'
                )

        for tournament in sce_tournaments:
            players = tournament.tournament_players
            for player in players:
                player_sce_id = SCEUtils.get_player_plugin_data(player).id
                if not self._sync_player(
                    player, sce_player_sync_data_by_id.get(player_sce_id or '')
                ):
                    conflict_count += 1

        event_plugin_data.deleted_player_ids = []
        event_plugin_data.last_sync_at = datetime.now()
        SCEUtils.update_event_plugin_data(self.event, event_plugin_data)
        log_suffix = (
            f'{conflict_count} player conflicts' if conflict_count else 'no conflicts'
        )
        self._log_sync_operation('Sync completed, ' + log_suffix, is_info=True)
        return not bool(conflict_count)
