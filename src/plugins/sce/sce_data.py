from dataclasses import dataclass, field
from datetime import datetime, date
from functools import cached_property
from typing import Any, Self

from common.i18n import _
from data.event import Event
from data.player import TournamentPlayer
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredTournament, StoredPlayer
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.manager import plugin_manager
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_mappers import SCEPlayerGender
from plugins.utils import PluginData
from utils.date_time import format_date, format_datetime
from utils.enum import TournamentRating, PlayerTitle, PlayerRatingType, PlayerGender
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
    rounds: int
    start_date: date
    stop_date: date
    round_schedule: dict[int, datetime]
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

    @cached_property
    def round_schedule_str(self) -> dict[int, str]:
        return {
            round_: format_datetime(datetime_)
            for round_, datetime_ in self.round_schedule.items()
        }

    @property
    def human_readable_time_control(self) -> str:
        if not self.time_control:
            return ''
        return trf25_to_human_readable(self.time_control)

    @classmethod
    def from_sce_data(cls, data: dict[str, Any]) -> Self:
        return cls(
            name=data['name'],
            type=TournamentRating.from_key(data['type']),
            rounds=data['number_of_rounds'],
            start_date=datetime.fromisoformat(data['start_date']).date(),
            stop_date=datetime.fromisoformat(data['end_date']).date(),
            time_control=data['time_control_trf26'],
            round_schedule={
                schedule['round']: datetime.fromisoformat(
                    f'{schedule["date"]} {schedule["time"]}'
                )
                for schedule in data['round_schedule']
            },
        )

    @classmethod
    def from_tournament(cls, tournament: Tournament) -> Self:
        return cls(
            name=tournament.name,
            type=tournament.rating,
            rounds=tournament.rounds,
            start_date=tournament.start_date,
            stop_date=tournament.stop_date,
            time_control=tournament.time_control_trf25 or None,
            round_schedule={
                round_: datetime_
                for round_, datetime_ in tournament.round_datetimes.items()
                if datetime_
            },
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
            # NOTE (Molrn) All fields added after the first usage
            # should be considered optional to not fail on previous data
            time_control=stored_value.get('time_control'),
            rounds=stored_value.get('rounds', 1),
            round_schedule={
                int(round_): SQLiteDatabase.load_datetime_from_database_field(datetime_)
                for round_, datetime_ in stored_value.get('round_schedule', {}).items()
            },
        )

    def round_restricted_schedule(self, max_round: int) -> dict[str, datetime | None]:
        return {
            str(round_): self.round_schedule.get(round_)
            for round_ in range(1, max_round + 1)
        }

    def merge_with_other_sync_data(self, other_data: Self, ref_data: Self) -> Self:
        from plugins.sce.utils import SCEUtils

        merged_stored_value = SCEUtils.merge_dicts(
            self.to_stored_value(),
            other_data.to_stored_value(),
            ref_data.to_stored_value(),
            ['round_schedule'],
        )
        merged_data = self.from_stored_value(merged_stored_value)
        max_round = merged_data.rounds
        merged_schedule = SCEUtils.merge_dicts(
            self.round_restricted_schedule(max_round),
            other_data.round_restricted_schedule(max_round),
            ref_data.round_restricted_schedule(max_round),
        )
        merged_data.round_schedule = {
            int(round_): datetime_
            for round_, datetime_ in merged_schedule.items()
            if datetime_
        }
        return merged_data

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'type': self.type.value,
            'rounds': self.rounds,
            'start_date': SQLiteDatabase.dump_date_to_database_field(self.start_date),
            'stop_date': SQLiteDatabase.dump_date_to_database_field(self.stop_date),
            'time_control': self.time_control,
            'round_schedule': {
                str(round_): SQLiteDatabase.dump_datetime_to_database_field(datetime_)
                for round_, datetime_ in self.round_schedule.items()
            },
        }

    def to_sce_data(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'type': self.type.form_key,
            'number_of_rounds': self.rounds,
            'start_date': SQLiteDatabase.dump_date_to_database_field(self.start_date),
            'end_date': SQLiteDatabase.dump_date_to_database_field(self.stop_date),
            'time_control_trf26': self.time_control,
            'round_schedule': [
                {
                    'round': round_,
                    'date': SQLiteDatabase.dump_date_to_database_field(
                        datetime_.date()
                    ),
                    'time': datetime_.strftime('%H:%M'),
                }
                for round_, datetime_ in self.round_schedule.items()
            ],
        }

    def augment_stored_tournament(
        self, stored_tournament: StoredTournament, event: Event
    ) -> None:
        stored_tournament.name = self.name
        stored_tournament.rating = self.type.value
        stored_tournament.rounds = self.rounds
        stored_tournament.start_date = self.start_date
        stored_tournament.stop_date = self.stop_date
        stored_tournament.time_control_trf25 = self.time_control
        stored_tournament.round_datetimes = {
            round_: self.round_schedule.get(round_)
            for round_ in range(1, self.rounds + 1)
        }
        plugin_data = SCETournamentPluginData.from_stored_value(
            stored_tournament.plugin_data.get(PLUGIN_NAME, {})
        )
        plugin_data.last_sync_data = self
        stored_tournament.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()

    @staticmethod
    def diff_fields_by_property_name() -> dict[str, str]:
        """Fields used to generate the values of the conflict modal."""
        return {
            'name': _('Name'),
            'type_str': _('Type'),
            'rounds': _('Rounds'),
            'start_date_str': _('Start'),
            'stop_date_str': _('End'),
            'human_readable_time_control': _('Time control'),
        }


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
    rating_type: PlayerRatingType | None = None
    national_id: str | None = None
    phone: str | None = None
    gender: PlayerGender = PlayerGender.NONE

    # Not stored
    mail: str | None = None

    @property
    def title_str(self) -> str:
        return self.title.short_name

    @property
    def rating_str(self) -> str:
        if self.rating and self.rating_type:
            return str(PlayerRatingAndType(self.rating, self.rating_type))
        return ''

    @property
    def gender_str(self) -> str:
        if self.gender == PlayerGender.NONE:
            return ''
        return self.gender.name

    @classmethod
    def from_sce_data(
        cls,
        data: dict[str, Any],
        tournament_id: str,
        with_mail: bool = False,
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
            rating_type=PlayerRatingType.from_key(data['rating_type'])
            if data['rating_type']
            else None,
            phone=data['phone_number'],
            gender=(
                SCEPlayerGender.get_core_object(data['gender'])
                if data['gender']
                else PlayerGender.NONE
            ),
            mail=data.get('user_email') if with_mail else None,
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
            rating_type=player.rating_type if player.rating else None,
            phone=player.phone,
            gender=player.gender,
        )
        plugin_manager.hook_for_event(
            player.event, 'augment_sce_player_sync_data_from_player'
        )(player=player, sync_data=sync_data)
        return sync_data

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        stored_rating_type = stored_value.get('rating_type')
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
            rating_type=PlayerRatingType(stored_rating_type)
            if stored_rating_type
            else None,
            phone=stored_value.get('phone'),
            gender=PlayerGender(stored_value.get('gender', PlayerGender.NONE)),
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
            'rating': self.rating or None,
            'rating_type': self.rating_type.value if self.rating_type else None,
            'phone': self.phone,
            'gender': self.gender.value,
        }

    def to_sce_data(self) -> dict[str, Any]:
        return self.to_stored_value() | {
            'year_of_birth': min(max(self.year_of_birth or 0, 1900), date.today().year),
            'rating_type': self.rating_type.key.upper() if self.rating_type else None,
            'phone_number': self.phone,
            'gender': SCEPlayerGender.get_outer_value(self.gender),
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
        stored_player.phone = self.phone
        stored_player.gender = self.gender.value
        if current_rating != self.rating or current_rating_type != self.rating_type:
            stored_player.ratings[tournament.rating.value] = PlayerRating.from_type(
                self.rating, self.rating_type or PlayerRatingType.ESTIMATED
            ).stored_value
        plugin_data = SCEPlayerPluginData.from_stored_value(
            stored_player.plugin_data.get(PLUGIN_NAME, {})
        )
        plugin_data.last_sync_data = self
        stored_player.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
        plugin_manager.hook_for_event(
            tournament.event, 'augment_stored_player_from_player_sync_data'
        )(stored_player=stored_player, sync_data=self)

    @staticmethod
    def diff_fields_by_property_name(event: Event) -> dict[str, str]:
        """Fields used to generate the values of the conflict modal."""
        diff_fields = {
            'last_name': _('Last name'),
            'first_name': _('First name'),
            'gender_str': _('Gender'),
            'fide_id': _('FIDE ID'),
            'national_id': '',
            'year_of_birth': _('Year of birth'),
            'title_str': _('Title'),
            'club': _('Club'),
            'rating_str': _('Rating'),
            'phone': _('Phone'),
        }
        national_id_label = plugin_manager.hook_for_event(
            event, 'get_sce_national_id_player_field_label'
        )()
        if national_id_label:
            diff_fields['national_id'] = national_id_label
        else:
            del diff_fields['national_id']
        return diff_fields


@dataclass
class SCEEventPluginData(PluginData):
    id: str | None = None
    slug: str | None = None
    organiser_slug: str | None = None
    status: str | None = None
    auto_upload: bool = True
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
            auto_upload=stored_value.get('auto_upload', True),
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
        return cls()

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return {}


@dataclass
class SCETournamentPluginData(PluginData):
    id: str | None = None
    auto_upload: bool = False
    last_upload_at: datetime | None = None
    last_upload_attempt_at: datetime | None = None
    upload_failure_id: str | None = None
    last_sync_data: SCETournamentSyncData | None = None
    conflict_sync_data: SCETournamentSyncData | None = None

    @property
    def last_upload_at_str(self) -> str:
        if not self.last_upload_at:
            return '-'
        return format_datetime(self.last_upload_at)

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        stored_last_sync_data = stored_value.get('last_sync_data')
        stored_conflict_sync_data = stored_value.get('conflict_sync_data')
        return cls(
            id=stored_value.get('id'),
            auto_upload=stored_value.get('auto_upload', False),
            last_upload_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_upload_at'),
            ),
            last_upload_attempt_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_upload_attempt_at'),
            ),
            upload_failure_id=stored_value.get('upload_failure_id'),
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
            'last_upload_attempt_at': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.last_upload_attempt_at
            ),
            'upload_failure_id': self.upload_failure_id,
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
