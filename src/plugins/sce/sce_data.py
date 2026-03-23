from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Self

from data.event import Event
from data.player import TournamentPlayer
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredTournament, StoredPlayer
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.manager import plugin_manager
from plugins.sce import PLUGIN_NAME
from plugins.utils import PluginData
from utils.date_time import format_date, format_datetime
from utils.enum import TournamentRating, PlayerTitle, PlayerRatingType
from utils.time_control import trf25_to_human_readable
from utils.types import PlayerRatingAndType, PlayerRating


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
    time_control: str | None = None

    @property
    def start_date_str(self) -> str:
        return format_date(self.start_date)

    @property
    def stop_date_str(self) -> str:
        return format_date(self.stop_date)

    @property
    def type_str(self) -> str:
        return self.type.short_name

    @property
    def human_readable_time_control(self) -> str:
        if not self.time_control:
            return '-'
        return trf25_to_human_readable(self.time_control)

    @classmethod
    def from_sce_data(cls, data: dict[str, Any]) -> Self:
        return cls(
            name=data['name'],
            type=TournamentRating.from_key(data['type']),
            start_date=datetime.fromisoformat(data['start_date']).date(),
            stop_date=datetime.fromisoformat(data['end_date']).date(),
            time_control=data['time_control_trf26'],
        )

    @classmethod
    def from_tournament(cls, tournament: Tournament) -> Self:
        return cls(
            name=tournament.name,
            type=tournament.rating,
            start_date=tournament.start_date,
            stop_date=tournament.stop_date,
            time_control=tournament.time_control_trf25,
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
            time_control=stored_value.get('time_control'),
        )

    def merge_with_other_sync_data(self, other_data: Self, ref_data: Self) -> Self:
        from plugins.sce.utils import SCEUtils

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
            'time_control': self.time_control,
        }

    def to_sce_data(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'type': self.type.form_key,
            'start_date': SQLiteDatabase.dump_date_to_database_field(self.start_date),
            'end_date': SQLiteDatabase.dump_date_to_database_field(self.stop_date),
            'time_control_trf26': self.time_control,
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
        stored_tournament.time_control_trf25 = self.time_control
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
        from plugins.sce.utils import SCEUtils

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
        from plugins.sce.utils import SCEUtils

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
    is_duplicated: bool = False

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
            is_duplicated=stored_value.get('is_duplicated', False),
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
            'is_duplicated': self.is_duplicated,
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
