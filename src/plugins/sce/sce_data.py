from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from functools import cached_property
from typing import Any, Self

from common.i18n import _
from data.criteria.managers import TournamentCriterionManager
from data.criteria.tournament_criteria import TournamentCriterion
from data.event import Event
from data.player import TournamentPlayer, Player, MIN_YOB
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredTournament, StoredPlayer
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.ffe.utils import PlayerFFELicence
from plugins.manager import plugin_manager
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_mappers import SCEPlayerGender, SCETournamentCriteria
from plugins.utils import PluginData
from utils import Utils
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
class SCEDuplicatedPlayer:
    last_name: str
    first_name: str | None
    duplicate_player_id: int | None = None

    @property
    def full_name(self) -> str:
        return Player.player_full_name(self.first_name, self.last_name)

    @classmethod
    def from_stored_value(cls, value: dict[str, Any]) -> Self:
        return cls(
            last_name=value['last_name'],
            first_name=value['first_name'],
            duplicate_player_id=value.get('duplicate_player_id'),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SCETournamentSyncData:
    name: str
    type: TournamentRating
    rounds: int
    start_date: date
    stop_date: date
    round_schedule: dict[int, datetime]
    time_control: str | None = None
    criteria: list[TournamentCriterion] = field(default_factory=list)

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
    def criteria_str(self) -> str:
        return ', '.join(criterion.full_name for criterion in self.criteria)

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
            criteria=SCETournamentCriteria.sce_data_to_core_value(
                data['criteria'] or {}
            ),
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
            criteria=list(tournament.criteria),
        )

    @classmethod
    def _stored_criteria_to_criteria(
        cls, stored_criteria: dict[str, Any]
    ) -> list[TournamentCriterion]:
        criteria: list[TournamentCriterion] = []
        for criteria_id, stored_value in stored_criteria.items():
            criterion = TournamentCriterionManager(None).get_object(criteria_id)
            value = criterion.value_from_stored_value(stored_value)
            criterion.set_value(value)
            criteria.append(criterion)
        return criteria

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
            criteria=cls._stored_criteria_to_criteria(stored_value.get('criteria', {})),
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
            'criteria': {
                criterion.id: criterion.stored_value for criterion in self.criteria
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
            'criteria': SCETournamentCriteria.core_value_to_sce_data(self.criteria),
        }

    def augment_stored_tournament(
        self, stored_tournament: StoredTournament, event: Event
    ) -> None:
        used_tournament_names = [
            tournament.name
            for tournament in event.tournaments
            if tournament.id != stored_tournament.id
        ]
        stored_tournament.name = Utils.get_unused_item_name(
            self.name, used_tournament_names
        )
        stored_tournament.rating = self.type.value
        stored_tournament.rounds = self.rounds
        stored_tournament.start_date = self.start_date
        stored_tournament.stop_date = self.stop_date
        stored_tournament.time_control_trf25 = self.time_control
        stored_tournament.round_datetimes = {
            round_: self.round_schedule.get(round_)
            for round_ in range(1, self.rounds + 1)
        }
        stored_tournament.criteria = {
            criterion.id: criterion.stored_value for criterion in self.criteria
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
            'criteria_str': _('Criteria'),
        }


@dataclass
class SCEFraSchoolSyncData:
    code: str
    label: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict_value(cls, value: dict[str, str] | None) -> Self | None:
        if not value:
            return None
        return cls(
            code=value['code'],
            label=value['label'],
        )


@dataclass
class SCEPlayerSyncData:
    tournament_id: str
    last_name: str
    first_name: str | None = None
    federation: str | None = None
    year_of_birth: int | None = None
    fide_id: int | None = None
    title: PlayerTitle = PlayerTitle.NONE
    club: str = ''
    rating: int | None = None
    rating_type: PlayerRatingType | None = None
    phone: str | None = None
    gender: PlayerGender = PlayerGender.NONE
    comment: str | None = None
    check_in: bool = False

    # Plugin fields
    national_id: str | None = None
    ffe_licence: PlayerFFELicence = PlayerFFELicence.NONE
    ffe_league: str | None = None
    fra_school: SCEFraSchoolSyncData | None = None

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

    @property
    def ffe_licence_str(self) -> str:
        return self.ffe_licence.short_name

    @property
    def fra_school_label_str(self) -> str:
        if not self.fra_school:
            return ''
        return self.fra_school.label

    @classmethod
    def from_sce_data(
        cls,
        event: 'Event',
        data: dict[str, Any],
        tournament_id: str,
        with_mail: bool = False,
    ) -> Self:
        yob = data['year_of_birth']
        sync_data = cls(
            tournament_id=tournament_id,
            last_name=data['last_name'].upper(),
            first_name=data['first_name'],
            federation=data['federation'],
            # As SC.com YOB are mandatory, consider 1900 as an
            # empty field to avoid setting it in the THP
            year_of_birth=yob if yob > MIN_YOB else None,
            fide_id=data['fide_id'],
            title=PlayerTitle(data['title'] or PlayerTitle.NONE),
            club=data['club'] or '',
            rating=data['rating'],
            rating_type=PlayerRatingType.from_key(data['rating_type'])
            if data['rating_type']
            else None,
            phone=data['phone_number'],
            comment=data['comment'],
            gender=(
                SCEPlayerGender.get_core_object(data['gender'])
                if data['gender']
                else PlayerGender.NONE
            ),
            check_in=data['checked_in'],
            mail=data.get('user_email') if with_mail else None,
        )
        plugin_manager.hook_for_event(
            event, 'augment_sce_player_sync_data_from_sce_data'
        )(sce_data=data, sync_data=sync_data)
        return sync_data

    @classmethod
    def from_player(cls, player: TournamentPlayer) -> Self:
        from plugins.sce.utils import SCEUtils

        tournament_id = SCEUtils.get_tournament_plugin_data(player.tournament).id
        assert tournament_id is not None
        yob = player.year_of_birth
        sync_data = cls(
            tournament_id=tournament_id,
            last_name=player.last_name,
            first_name=player.first_name,
            year_of_birth=yob if yob > MIN_YOB else None,
            fide_id=player.fide_id,
            title=player.title,
            club=player.club.name,
            federation=player.federation.name,
            rating=player.rating,
            rating_type=player.rating_type if player.rating else None,
            phone=player.phone,
            gender=player.gender,
            comment=player.comment or None,
            check_in=player.check_in,
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
            federation=stored_value.get('federation'),
            club=stored_value.get('club', ''),
            rating=stored_value.get('rating'),
            rating_type=PlayerRatingType(stored_rating_type)
            if stored_rating_type
            else None,
            phone=stored_value.get('phone'),
            gender=PlayerGender(stored_value.get('gender', PlayerGender.NONE)),
            ffe_league=stored_value.get('ffe_league'),
            ffe_licence=PlayerFFELicence(
                stored_value.get('ffe_licence') or PlayerFFELicence.NONE
            ),
            comment=stored_value.get('comment'),
            check_in=stored_value.get('check_in', False),
            fra_school=SCEFraSchoolSyncData.from_dict_value(
                stored_value.get('fra_school')
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
            'federation': self.federation,
            'club': self.club,
            'rating': self.rating or None,
            'rating_type': self.rating_type.value if self.rating_type else None,
            'phone': self.phone,
            'gender': self.gender.value,
            'ffe_licence': (
                self.ffe_licence.value
                if self.ffe_licence != PlayerFFELicence.NONE
                else None
            ),
            'ffe_league': self.ffe_league,
            'comment': self.comment,
            'check_in': self.check_in,
            'fra_school': self.fra_school.to_dict() if self.fra_school else None,
        }

    def to_sce_data(self) -> dict[str, Any]:
        return {
            'tournament_id': self.tournament_id,
            'last_name': self.last_name,
            'first_name': self.first_name,
            'year_of_birth': self.year_of_birth or MIN_YOB,
            'fide_id': self.fide_id,
            'national_id': self.national_id,
            'title': self.title.value,
            'federation': self.federation,
            'club': self.club,
            'rating': self.rating or None,
            'rating_type': self.rating_type.key.upper() if self.rating_type else None,
            'phone': self.phone,
            'gender': SCEPlayerGender.get_outer_value(self.gender),
            'ffe_licence_type': (
                self.ffe_licence.value
                if self.ffe_licence != PlayerFFELicence.NONE
                else None
            ),
            'ffe_league': self.ffe_league,
            'phone_number': self.phone,
            'comment': self.comment,
            'checked_in': self.check_in,
            'fra_school_code': self.fra_school.code if self.fra_school else None,
            'fra_school_label': self.fra_school.label if self.fra_school else None,
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
        event = tournament.event
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
        stored_player.federation = self.federation or event.federation
        stored_player.club = self.club
        stored_player.phone = self.phone
        stored_player.gender = self.gender.value
        stored_player.comment = self.comment
        stored_player.check_in = self.check_in
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
            event, 'augment_stored_player_from_sce_player_sync_data'
        )(event=event, stored_player=stored_player, sync_data=self)

    @staticmethod
    def diff_fields_by_property_name(event: Event) -> dict[str, str]:
        """Fields used to generate the values of the conflict modal."""
        diff_fields = {
            'last_name': _('Last name'),
            'first_name': _('First name'),
            'title_str': _('Title'),
            'rating_str': _('Rating'),
            'fra_school_label_str': None,
            'federation': _('Federation'),
            'ffe_league': None,
            'club': _('Club'),
            'year_of_birth': _('Year of birth'),
            'gender_str': _('Gender'),
            'fide_id': _('FIDE ID'),
            'national_id': None,
            'ffe_licence_str': None,
            'phone': _('Phone'),
            'comment': _('Comment'),
        }
        plugin_manager.hook_for_event(event, 'update_sce_player_diff_field_labels')(
            diff_fields=diff_fields
        )
        return {key: label for key, label in diff_fields.items() if label is not None}


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
    check_in_open: bool = False
    check_in_opens_at: datetime | None = None
    check_in_closes_at: datetime | None = None
    last_sync_data: SCETournamentSyncData | None = None
    conflict_sync_data: SCETournamentSyncData | None = None
    duplicated_players_by_id: dict[str, SCEDuplicatedPlayer] = field(
        default_factory=dict
    )

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
            check_in_open=stored_value.get('check_in_open', False),
            check_in_opens_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('check_in_opens_at')
            ),
            check_in_closes_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('check_in_closes_at')
            ),
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
            duplicated_players_by_id={
                id_: SCEDuplicatedPlayer.from_stored_value(stored_dup_player)
                for id_, stored_dup_player in stored_value.get(
                    'duplicated_players_by_id', {}
                ).items()
            },
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
            'check_in_open': self.check_in_open,
            'check_in_opens_at': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.check_in_opens_at
            ),
            'check_in_closes_at': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.check_in_closes_at
            ),
            'last_sync_data': (
                self.last_sync_data.to_stored_value() if self.last_sync_data else None
            ),
            'conflict_sync_data': (
                self.conflict_sync_data.to_stored_value()
                if self.conflict_sync_data
                else None
            ),
            'duplicated_players_by_id': {
                id_: dup_player.to_stored_value()
                for id_, dup_player in self.duplicated_players_by_id.items()
            },
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

    @staticmethod
    def _schedule_tooltip_section(title: str, datetime_: datetime | None) -> str:
        if not datetime_:
            return ''
        return (
            f'<div class="text-center fw-bold">{title}</div>'
            f'<div class="text-center">{format_datetime(datetime_)}</div>'
        )

    @property
    def check_in_schedule_tooltip(self) -> str:
        return self._schedule_tooltip_section(
            _('Opening'), self.check_in_opens_at
        ) + self._schedule_tooltip_section(_('Closing'), self.check_in_closes_at)


@dataclass
class SCEPlayerPluginData(PluginData):
    id: str | None = None
    deleted_id: str | None = None
    last_sync_data: SCEPlayerSyncData | None = None
    conflict_sync_data: SCEPlayerSyncData | None = None
    duplicated_registration_id: str | None = None
    _legacy_is_duplicated: bool = False

    @property
    def is_duplicated(self) -> bool:
        return self._legacy_is_duplicated or bool(self.duplicated_registration_id)

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
            duplicated_registration_id=stored_value.get('duplicated_registration_id'),
            _legacy_is_duplicated=stored_value.get('is_duplicated', False),
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
            'duplicated_registration_id': self.duplicated_registration_id,
            'is_duplicated': self._legacy_is_duplicated,
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
