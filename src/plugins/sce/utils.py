import json
from dataclasses import dataclass, field
from datetime import datetime, date
from functools import partial
from logging import Logger
from typing import Any, Self

from common import SharlyChessException
from common.logger import get_logger
from common.network import NetworkMonitor
from data.event import Event
from data.player import Player, TournamentPlayer
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer, StoredTournament
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.manager import plugin_manager
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_event_status import (
    SCEEventStatus,
    NoInternetSCEEventStatus,
    InvalidRefreshTokenSCEEventStatus,
    NotConnectedSCEEventStatus,
)
from plugins.sce.sce_managers import (
    SCETournamentStatusManager,
    SCEEventStatusManager,
    SCESyncStatusManager,
)
from plugins.sce.sce_sync_status import SCESyncStatus, NeverSyncedSCESyncStatus
from plugins.sce.sce_tournament_status import (
    SCETournamentStatus,
    ModifiedSCETournamentStatus,
    PendingSCETournamentStatus,
    NotStartedSCETournamentStatus,
    NeverUploadedSCETournamentStatus,
    OngoingSCETournamentStatus,
    UpToDateSCETournamentStatus,
)
from plugins.utils import PluginData, PluginUtils
from utils import Utils
from utils.date_time import format_date_range, format_datetime
from utils.enum import PlayerTitle, PlayerRatingType, TournamentRating
from utils.types import PlayerRating, PlayerRatingAndType
from web.urls import build_get_url

logger: Logger = get_logger()

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


@dataclass
class SCETokens:
    access_token: str
    refresh_token: str
    expires_at: datetime


@dataclass
class SCETournamentSyncData:
    name: str
    type: TournamentRating
    start_date: date
    stop_date: date

    @property
    def date_range_str(self) -> str:
        return format_date_range(self.start_date, self.stop_date)

    @property
    def type_str(self) -> str:
        return self.type.short_name

    @classmethod
    def from_sce_data(cls, data: dict[str, Any]) -> Self:
        return cls(
            name=data['name'],
            type=TournamentRating.from_key(data['type']),
            start_date=datetime.fromisoformat(data['start_date']).date(),
            stop_date=datetime.fromisoformat(data['end_date']).date(),
        )

    @classmethod
    def from_tournament(cls, tournament: Tournament) -> Self:
        return cls(
            name=tournament.name,
            type=tournament.rating,
            start_date=tournament.start_date,
            stop_date=tournament.stop_date,
        )

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            name=stored_value['name'],
            type=TournamentRating(stored_value['type']),
            start_date=SQLiteDatabase.load_date_from_database_field(
                stored_value['start_date']
            ),
            stop_date=SQLiteDatabase.load_date_from_database_field(
                stored_value['stop_date']
            ),
        )

    def merge_with_other_sync_data(self, other_data: Self, ref_data: Self) -> Self:
        merged_stored_value = SCEUtils.merge_dicts(
            self.to_stored_value(),
            other_data.to_stored_value(),
            ref_data.to_stored_value(),
        )
        return self.from_stored_value(merged_stored_value)

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'type': self.type.value,
            'start_date': SQLiteDatabase.dump_date_to_database_field(self.start_date),
            'stop_date': SQLiteDatabase.dump_date_to_database_field(self.stop_date),
        }

    def to_sce_data(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'type': self.type.form_key,
            'start_date': SQLiteDatabase.dump_date_to_database_field(self.start_date),
            'end_date': SQLiteDatabase.dump_date_to_database_field(self.stop_date),
        }

    def augment_stored_tournament(
        self, stored_tournament: StoredTournament, event: Event
    ) -> None:
        stored_tournament.name = self.name
        stored_tournament.rating = self.type.value
        if (event.start_date, event.stop_date) == (self.start_date, self.stop_date):
            stored_tournament.start_date = None
            stored_tournament.stop_date = None
        else:
            stored_tournament.start_date = self.start_date
            stored_tournament.stop_date = self.stop_date
        plugin_data = SCETournamentPluginData.from_stored_value(
            stored_tournament.plugin_data.get(PLUGIN_NAME, {})
        )
        plugin_data.last_sync_data = self
        stored_tournament.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()


@dataclass
class SCEPlayerSyncData:
    tournament_id: str
    last_name: str
    first_name: str | None = None
    year_of_birth: int | None = None
    fide_id: int | None = None
    title: PlayerTitle = PlayerTitle.NONE
    club: str = ''
    rating: int | None = None
    rating_type: PlayerRatingType = PlayerRatingType.ESTIMATED
    national_id: str | None = None

    @property
    def title_str(self) -> str:
        return self.title.short_name or '-'

    @property
    def rating_str(self) -> str:
        return str(PlayerRatingAndType(self.rating or 0, self.rating_type))

    @classmethod
    def from_sce_data(
        cls,
        data: dict[str, Any],
        tournament_id: str,
    ) -> Self:
        return cls(
            tournament_id=tournament_id,
            last_name=data['last_name'].upper(),
            first_name=data['first_name'],
            year_of_birth=data['year_of_birth'],
            fide_id=data['fide_id'],
            national_id=data['national_id'],
            title=PlayerTitle(data['title'] or PlayerTitle.NONE),
            club=data['club'] or '',
            rating=data['rating'],
            rating_type=PlayerRatingType.from_key(
                data['rating_type'] or PlayerRatingType.ESTIMATED.key
            ),
        )

    @classmethod
    def from_player(cls, player: TournamentPlayer) -> Self:
        tournament_id = SCEUtils.get_tournament_plugin_data(player.tournament).id
        assert tournament_id is not None
        sync_data = cls(
            tournament_id=tournament_id,
            last_name=player.last_name,
            first_name=player.first_name,
            year_of_birth=player.year_of_birth,
            fide_id=player.fide_id,
            title=player.title,
            club=player.club.name,
            rating=player.rating,
            rating_type=player.rating_type,
        )
        plugin_manager.hook_for_event(
            player.event, 'augment_sce_player_sync_data_from_player'
        )(player=player, sync_data=sync_data)
        return sync_data

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            tournament_id=stored_value['tournament_id'],
            last_name=stored_value['last_name'],
            first_name=stored_value.get('first_name'),
            year_of_birth=stored_value.get('year_of_birth'),
            fide_id=stored_value.get('fide_id'),
            national_id=stored_value.get('national_id'),
            title=PlayerTitle(stored_value.get('title', PlayerTitle.NONE)),
            club=stored_value.get('club', ''),
            rating=stored_value.get('rating'),
            rating_type=PlayerRatingType(
                stored_value.get('rating_type', PlayerRatingType.ESTIMATED)
            ),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'tournament_id': self.tournament_id,
            'last_name': self.last_name,
            'first_name': self.first_name,
            'year_of_birth': self.year_of_birth,
            'fide_id': self.fide_id,
            'national_id': self.national_id,
            'title': self.title.value,
            'club': self.club,
            'rating': self.rating,
            'rating_type': self.rating_type.value,
        }

    def to_sce_data(self) -> dict[str, Any]:
        return self.to_stored_value() | {
            'year_of_birth': min(max(self.year_of_birth or 0, 1900), date.today().year),
            'rating_type': self.rating_type.key.upper(),
        }

    def merge_with_other_sync_data(self, other_data: Self, ref_data: Self) -> Self:
        merged_stored_value = SCEUtils.merge_dicts(
            self.to_stored_value(),
            other_data.to_stored_value(),
            ref_data.to_stored_value(),
        )
        return self.from_stored_value(merged_stored_value)

    def augment_stored_player(
        self,
        stored_player: StoredPlayer,
        tournament: Tournament,
        current_rating: int | None = None,
        current_rating_type: PlayerRatingType | None = None,
    ) -> None:
        stored_player.first_name = self.first_name
        stored_player.last_name = self.last_name
        if self.year_of_birth and not (
            stored_player.date_of_birth
            and self.year_of_birth != stored_player.date_of_birth.year
        ):
            stored_player.date_of_birth = None
            stored_player.year_of_birth = self.year_of_birth
        stored_player.fide_id = self.fide_id
        stored_player.title = self.title.value
        stored_player.club = self.club
        if current_rating != self.rating or current_rating_type != self.rating_type:
            stored_player.ratings[tournament.rating.value] = PlayerRating.from_type(
                self.rating, self.rating_type
            ).stored_value
        plugin_data = SCEPlayerPluginData.from_stored_value(
            stored_player.plugin_data.get(PLUGIN_NAME, {})
        )
        plugin_data.last_sync_data = self
        stored_player.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
        plugin_manager.hook_for_event(
            tournament.event, 'augment_stored_player_from_player_sync_data'
        )(stored_player=stored_player, sync_data=self)


@dataclass
class SCEEventPluginData(PluginData):
    id: str | None = None
    slug: str | None = None
    organiser_slug: str | None = None
    status: str | None = None
    auto_upload: bool = False
    auto_player_sync: bool = False
    tournament_names_by_id: dict[str, str] = field(default_factory=dict)
    last_sync_at: datetime | None = None
    last_sync_attempt_at: datetime | None = None
    last_sync_attempt_status: str | None = None
    deleted_player_ids: list[str] = field(default_factory=list)
    tokens: SCETokens | None = None

    @property
    def last_sync_str(self) -> str:
        assert self.last_sync_at is not None
        return format_datetime(self.last_sync_at)

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        tokens: SCETokens | None = None
        if stored_tokens := stored_value.get('tokens'):
            tokens = SCETokens(
                access_token=stored_tokens.get('access_token'),
                refresh_token=stored_tokens.get('refresh_token'),
                expires_at=SQLiteDatabase.load_datetime_from_database_field(
                    stored_tokens.get('expires_at'),
                ),
            )
        return cls(
            id=stored_value.get('id', ''),
            slug=stored_value.get('slug', ''),
            organiser_slug=stored_value.get('organiser_slug', ''),
            status=stored_value.get('status'),
            auto_upload=stored_value.get('auto_upload', False),
            auto_player_sync=stored_value.get('auto_player_sync', False),
            tournament_names_by_id=stored_value.get('tournament_names_by_id', {}),
            deleted_player_ids=stored_value.get('deleted_player_ids', []),
            tokens=tokens,
            last_sync_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_sync_at'),
            ),
            last_sync_attempt_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_sync_attempt_at'),
            ),
            last_sync_attempt_status=stored_value.get('last_sync_attempt_status'),
        )

    def to_stored_value(self) -> dict[str, Any]:
        stored_value: dict[str, Any] = {
            'id': self.id,
            'auto_upload': self.auto_upload,
            'auto_player_sync': self.auto_player_sync,
            'tournament_names_by_id': self.tournament_names_by_id,
            'deleted_player_ids': self.deleted_player_ids,
            'slug': self.slug,
            'organiser_slug': self.organiser_slug,
            'status': self.status,
            'last_sync_at': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.last_sync_at
            ),
            'last_sync_attempt_at': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.last_sync_attempt_at
            ),
            'last_sync_attempt_status': self.last_sync_attempt_status,
        }
        if self.tokens:
            stored_value['tokens'] = {
                'access_token': self.tokens.access_token,
                'refresh_token': self.tokens.refresh_token,
                'expires_at': (
                    SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                        self.tokens.expires_at
                    )
                ),
            }
        return stored_value

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        if previous_object:
            return previous_object
        return cls(id='')

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return {}


@dataclass
class SCETournamentPluginData(PluginData):
    id: str | None = None
    auto_upload: bool = True
    last_upload_at: datetime | None = None
    upload_status: str | None = None
    last_sync_data: SCETournamentSyncData | None = None
    conflict_sync_data: SCETournamentSyncData | None = None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        stored_last_sync_data = stored_value.get('last_sync_data')
        stored_conflict_sync_data = stored_value.get('conflict_sync_data')
        return cls(
            id=stored_value.get('id'),
            auto_upload=stored_value.get('auto_upload', True),
            last_upload_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_upload_at'),
            ),
            upload_status=stored_value.get('upload_status'),
            last_sync_data=(
                SCETournamentSyncData.from_stored_value(stored_last_sync_data)
                if stored_last_sync_data
                else None
            ),
            conflict_sync_data=(
                SCETournamentSyncData.from_stored_value(stored_conflict_sync_data)
                if stored_conflict_sync_data
                else None
            ),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'auto_upload': self.auto_upload,
            'last_upload_at': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.last_upload_at
            ),
            'upload_status': self.upload_status,
            'last_sync_data': (
                self.last_sync_data.to_stored_value() if self.last_sync_data else None
            ),
            'conflict_sync_data': (
                self.conflict_sync_data.to_stored_value()
                if self.conflict_sync_data
                else None
            ),
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        if previous_object and action != 'clone':
            return previous_object
        return cls()

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return {}


@dataclass
class SCEPlayerPluginData(PluginData):
    id: str | None = None
    deleted_id: str | None = None
    last_sync_data: SCEPlayerSyncData | None = None
    conflict_sync_data: SCEPlayerSyncData | None = None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        stored_last_sync_data = stored_value.get('last_sync_data')
        stored_conflict_sync_data = stored_value.get('conflict_sync_data')
        return cls(
            id=stored_value.get('id'),
            deleted_id=stored_value.get('deleted_id'),
            last_sync_data=(
                SCEPlayerSyncData.from_stored_value(stored_last_sync_data)
                if stored_last_sync_data
                else None
            ),
            conflict_sync_data=(
                SCEPlayerSyncData.from_stored_value(stored_conflict_sync_data)
                if stored_conflict_sync_data
                else None
            ),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'deleted_id': self.deleted_id,
            'last_sync_data': (
                self.last_sync_data.to_stored_value() if self.last_sync_data else None
            ),
            'conflict_sync_data': (
                self.conflict_sync_data.to_stored_value()
                if self.conflict_sync_data
                else None
            ),
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        if previous_object:
            return previous_object
        return cls()

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return {}


class SCEUtils:
    @staticmethod
    def get_event_plugin_data(event: Event) -> SCEEventPluginData:
        plugin_data = event.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, SCEEventPluginData)
        return plugin_data

    @staticmethod
    def get_tournament_plugin_data(tournament: Tournament) -> SCETournamentPluginData:
        plugin_data = tournament.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, SCETournamentPluginData)
        return plugin_data

    @staticmethod
    def get_player_plugin_data(player: Player) -> SCEPlayerPluginData:
        plugin_data = player.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, SCEPlayerPluginData)
        return plugin_data

    @staticmethod
    def update_event_plugin_data(
        event: Event,
        plugin_data: SCEEventPluginData,
        write: bool = True,
        write_stored_object: bool = False,
    ):
        event.stored_event.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
        event.plugin_data[PLUGIN_NAME] = plugin_data
        if write:
            with EventDatabase(event.uniq_id, True) as database:
                if write_stored_object:
                    database.update_stored_event(event.stored_event)
                else:
                    database.execute(
                        "UPDATE info SET plugin_data = json_set(plugin_data,'$.sce', json(?))",
                        (json.dumps(plugin_data.to_stored_value()),),
                    )

    @staticmethod
    def update_tournament_plugin_data(
        tournament: Tournament,
        plugin_data: SCETournamentPluginData,
        write: bool = True,
        write_stored_object: bool = False,
    ):
        tournament.stored_tournament.plugin_data[PLUGIN_NAME] = (
            plugin_data.to_stored_value()
        )
        tournament.plugin_data[PLUGIN_NAME] = plugin_data
        if write:
            with EventDatabase(tournament.event.uniq_id, write=True) as database:
                if write_stored_object:
                    database.update_stored_tournament(tournament.stored_tournament)
                else:
                    database.execute(
                        'UPDATE tournament SET plugin_data = '
                        "json_set(plugin_data,'$.sce', json(?)) WHERE id = ?",
                        (json.dumps(plugin_data.to_stored_value()), tournament.id),
                    )

    @staticmethod
    def update_player_plugin_data(
        player: Player,
        plugin_data: SCEPlayerPluginData,
        write: bool = True,
        write_stored_object: bool = False,
    ):
        player.stored_player.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
        player.plugin_data[PLUGIN_NAME] = plugin_data
        if write:
            with EventDatabase(player.event.uniq_id, write=True) as database:
                if write_stored_object:
                    database.update_stored_player(player.stored_player)
                else:
                    database.execute(
                        'UPDATE player SET plugin_data = '
                        "json_set(plugin_data,'$.sce', json(?)) WHERE id = ?",
                        (json.dumps(plugin_data.to_stored_value()), player.id),
                    )

    @classmethod
    def get_event_sce_tournaments(cls, event: Event) -> list[Tournament]:
        return [
            tournament
            for tournament in event.sorted_tournaments
            if cls.get_tournament_plugin_data(tournament).id
        ]

    @classmethod
    def get_tournament_by_sce_id(cls, event: Event, sce_id: str) -> Tournament:
        for tournament in event.tournaments:
            if cls.get_tournament_plugin_data(tournament).id == sce_id:
                return tournament
        raise ValueError('Tournament not found')

    @staticmethod
    def merge_dicts(
        dict1: dict[str, Any],
        dict2: dict[str, Any],
        ref_dict: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge 2 dicts with the same keys into one, according to the values of a ref dict.
        In case of inequality between 2 fields, choose the one that is different from the ref.
        If both are different from the ref, raise a SharlyChessException as the dicts can't be merged."""
        merged_dict: dict[str, Any] = {}
        for key, ref_value in ref_dict.items():
            value1 = dict1[key]
            value2 = dict2[key]
            if value1 == value2:
                merged_dict[key] = value1
            elif value1 == ref_value:
                merged_dict[key] = value2
            elif value2 == ref_value:
                merged_dict[key] = value1
            else:
                raise SharlyChessException(
                    f'Field [{key}] is not mergeable '
                    f'({value1=}, {value2=}, {ref_value=})'
                )
        return merged_dict

    @classmethod
    def resolve_tournament_upload_statuses(
        cls, tournament: Tournament
    ) -> list[SCETournamentStatus]:
        from plugins.sce.sce_background_uploader import (
            is_upload_ongoing,
            is_upload_queued,
            is_upload_scheduled,
        )

        plugin_data = cls.get_tournament_plugin_data(tournament)
        if not tournament.started:
            return [NotStartedSCETournamentStatus()]

        statuses: list[SCETournamentStatus] = []

        # Last upload status
        try:
            status = SCETournamentStatusManager().get_object(
                plugin_data.upload_status or ''
            )
            statuses.append(status)
        except KeyError:
            pass

        is_modified = cls.tournament_modified_since_last_upload(tournament)
        # Current data status
        if not plugin_data.last_upload_at:
            statuses.append(NeverUploadedSCETournamentStatus())
        elif is_modified:
            statuses.append(ModifiedSCETournamentStatus())
        else:
            statuses.append(UpToDateSCETournamentStatus())

        # Next upload status
        if is_upload_ongoing(tournament):
            statuses.append(OngoingSCETournamentStatus())
        elif is_upload_queued(tournament) or (
            is_upload_scheduled(tournament) and is_modified
        ):
            statuses.append(PendingSCETournamentStatus())
        return statuses

    @classmethod
    def resolve_event_status(cls, event: Event) -> SCEEventStatus:
        plugin_data = cls.get_event_plugin_data(event)
        if not plugin_data.id or not plugin_data.status:
            return NotConnectedSCEEventStatus()
        if not NetworkMonitor.connected():
            return NoInternetSCEEventStatus()
        if not plugin_data.tokens:
            return InvalidRefreshTokenSCEEventStatus()

        return SCEEventStatusManager().get_object(plugin_data.status)

    @classmethod
    def resolve_last_sync_status(cls, event: Event) -> SCESyncStatus:
        plugin_data = cls.get_event_plugin_data(event)
        try:
            return SCESyncStatusManager().get_object(
                plugin_data.last_sync_attempt_status or ''
            )
        except KeyError:
            return NeverSyncedSCESyncStatus()

    @classmethod
    def tournament_modified_since_last_upload(
        cls, tournament: Tournament | StoredTournament
    ) -> bool:
        last_upload = cls.get_tournament_last_upload(tournament)
        return not last_upload or Utils.tournament_results_modified_since(
            tournament, last_upload
        )

    @classmethod
    def get_tournament_last_upload(
        cls, tournament: Tournament | StoredTournament
    ) -> datetime | None:
        if isinstance(tournament, Tournament):
            plugin_data = cls.get_tournament_plugin_data(tournament)
        else:
            plugin_data = SCETournamentPluginData.from_stored_value(
                tournament.plugin_data.get(PLUGIN_NAME, {})
            )
        return plugin_data.last_upload_at

    @classmethod
    def event_url(cls, event: Event) -> str:
        from plugins.sce.sce_session import SCE_BASE_URL

        pd = cls.get_event_plugin_data(event)
        return build_get_url(
            SCE_BASE_URL, f'/organizer/{pd.organiser_slug}/events/{pd.id}'
        )

    @classmethod
    def tournament_url(cls, tournament: Tournament) -> str:
        from plugins.sce.sce_session import SCE_BASE_URL

        pd = cls.get_event_plugin_data(tournament.event)
        tournament_id = cls.get_tournament_plugin_data(tournament).id
        return build_get_url(
            SCE_BASE_URL,
            f'/organizer/{pd.organiser_slug}/events/'
            f'{pd.id}/tournaments/{tournament_id}',
        )
