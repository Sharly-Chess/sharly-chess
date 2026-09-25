import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from functools import partial
from typing import Self, Any, TYPE_CHECKING

from common.i18n import _, pgettext
from data.account import Account
from data.event import Event
from data.player import Player
from data.tournament import Tournament
from data.tournament_period import TournamentPeriod
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_upload_status import (
    FFEUploadStatus,
    NeverUploadedFFEUploadStatus,
    FailureFFEUploadStatus,
    NetworkFailureFFEUploadStatus,
    UnexpectedFailureFFEUploadStatus,
    ModifiedFFEUploadStatus,
    UpToDateFFEUploadStatus,
    OngoingFFEUploadStatus,
    PendingFFEUploadStatus,
    NotConfiguredFFEUploadStatus,
    IncompatibleFFEUploadStatus,
    NotReachableFFEUploadStatus,
    AuthFailureFFEUploadStatus,
    FinishedFailureFFEUploadStatus,
    PapiConversionFailureFFEUploadStatus,
    GroupNotFoundFFEUploadStatus,
    RejectedFFEUploadStatus,
)
from plugins.utils import PluginUtils, PluginData, AccountPluginData
from utils.date_time import format_datetime
from utils.entity import EntityManager

if TYPE_CHECKING:
    from data.pairings.systems import PairingSystem
    from data.rule_sets.rule_sets import RuleSet
from utils.enum import FormAction
from web.controllers.base_controller import WebContext

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)

FFE_UPLOAD_DELAY = 3
FFE_EPOCH = datetime(2000, 1, 1)

# The FFE league names.
FFE_LEAGUES: dict[str, str] = {
    'ARA': 'Auvergne-Rhône-Alpes',
    'BFC': 'Bourgogne-Franche-Comté',
    'BRE': 'Bretagne',
    'CRS': 'Corse',
    'CVL': 'Centre-Val de Loire',
    'EST': 'Grand-Est',
    'GUA': 'Guadeloupe',
    'GUY': 'Guyane',
    'HDF': 'Hauts-de-France',
    'IDF': 'Île-de-France',
    'MAR': 'Martinique',
    'NAQ': 'Nouvelle-Aquitaine',
    'NCA': 'Nouvelle-Calédonie',
    'NOR': 'Normandie',
    'OCC': 'Occitanie',
    'PAC': "Provence-Alpes-Côte d'azur",
    'PDL': 'Pays de la Loire',
    'POL': 'Saint-Pierre-et-Miquelon',
    'REU': 'Réunion',
}


class FFEUtils:
    @staticmethod
    def system_supports_ffe_transfer(
        event: Event, pairing_system: 'PairingSystem'
    ) -> bool:
        """Whether the Papi upload (and its fields) is offered for a
        tournament of ``event`` paired with this system: it needs a
        game-point score, and every tournament of a team event is sent
        through the site's team module instead. A Scheveningen still
        exports a Papi file by hand — that export has its own rules."""
        if not pairing_system.uses_result_points:
            return False
        return not event.is_team_event

    @staticmethod
    def rule_set_team_competition_id(rule_set: 'RuleSet | None') -> int | None:
        """The FFE team-module competition of *rule_set*, ``None`` when it
        is not an FFE team competition."""
        from plugins.ffe.ffe_rule_sets import _FfeTeamCupRuleSet

        if not isinstance(rule_set, _FfeTeamCupRuleSet):
            return None
        return rule_set.ffe_competition_id()

    @classmethod
    def team_competition_id(cls, tournament: Tournament) -> int | None:
        """The FFE team-module competition this tournament is sent to:
        the one its rule set names, else the one chosen in the form."""
        if not cls.supports_team_transfer(tournament):
            return None
        return (
            cls.rule_set_team_competition_id(tournament.rule_set)
            or cls.get_tournament_plugin_data(tournament).team_competition_id
        )

    @staticmethod
    def supports_team_transfer(tournament: Tournament) -> bool:
        """Whether the tournament is sent through the site's team module
        (match reports, one per round and pair of teams) rather than as
        a Papi file: every tournament of a team event is."""
        return tournament.event.is_team_event

    @staticmethod
    def supports_ffe_transfer(tournament: Tournament) -> bool:
        """Whether the FFE-site transfer is offered for this tournament —
        see :meth:`system_supports_ffe_transfer` and
        :meth:`supports_team_transfer`."""
        return FFEUtils.system_supports_ffe_transfer(
            tournament.event, tournament.pairing_system
        ) or FFEUtils.supports_team_transfer(tournament)

    @staticmethod
    def event_supports_ffe_transfer(event: Event) -> bool:
        """Whether any tournament of the event offers the FFE-site transfer
        — the test for the event-level transfer entry."""
        if not event.is_team_event:
            return True
        return any(
            FFEUtils.supports_ffe_transfer(tournament)
            for tournament in event.tournaments
        )

    @classmethod
    def team_transfer_configured(cls, tournament: Tournament) -> bool:
        """Whether the tournament names the group its match reports go
        to, and the account that may write them. The competition comes
        from the rule set when it names one, so it need not be stored."""
        pd = cls.get_tournament_plugin_data(tournament)
        return bool(
            pd.team_login
            and pd.team_password
            and pd.team_division_id
            and pd.team_group_id
            and cls.team_competition_id(tournament)
        )

    @classmethod
    def is_configured(cls, tournament: Tournament) -> bool:
        """Whether the tournament holds the credentials its transfer needs."""
        if cls.supports_team_transfer(tournament):
            return cls.team_transfer_configured(tournament)
        pd = cls.get_tournament_plugin_data(tournament)
        return bool(pd.ffe_id and pd.password)

    @classmethod
    def resolve_auto_upload(cls, tournament: Tournament) -> bool:
        if not cls.get_event_plugin_data(tournament.event).auto_upload:
            return False
        return cls.get_tournament_plugin_data(tournament).auto_upload

    @staticmethod
    def get_event_plugin_data(event: Event) -> 'FfeEventPluginData':
        plugin_data = event.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, FfeEventPluginData)
        return plugin_data

    @staticmethod
    def get_tournament_plugin_data(tournament: Tournament) -> 'FfeTournamentPluginData':
        plugin_data = tournament.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, FfeTournamentPluginData)
        return plugin_data

    @staticmethod
    def get_period_own_plugin_data(
        period: 'TournamentPeriod',
    ) -> 'FfeTournamentPluginData':
        """What the period itself holds — its own registration and the
        outcome of its own uploads, with nothing borrowed from the
        tournament."""
        plugin_data = period.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, FfeTournamentPluginData)
        return plugin_data

    @staticmethod
    def get_period_plugin_data(period: 'TournamentPeriod') -> 'FfeTournamentPluginData':
        """What a rating period is submitted under.

        Each tranche has its own homologation number; the first tranche
        is submitted under the tournament's own, which is also where the
        whole tournament is published for the players. A later tranche
        with no registration of its own falls back to it too, so that a
        tournament nobody has cut up yet still uploads."""
        if period.first_round > 1:
            plugin_data = FFEUtils.get_period_own_plugin_data(period)
            if plugin_data.ffe_id:
                return plugin_data
        return FFEUtils.get_tournament_plugin_data(period.tournament)

    @staticmethod
    def get_player_plugin_data(player: Player) -> 'FfePlayerPluginData':
        plugin_data = player.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, FfePlayerPluginData)
        return plugin_data

    @staticmethod
    def get_account_plugin_data(account: Account) -> 'FfeAccountPluginData':
        plugin_data = account.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, FfeAccountPluginData)
        return plugin_data

    @classmethod
    def upload_unavailable_message(cls, tournament: Tournament) -> str | None:
        """Why the tournament's data cannot be sent to the FFE website,
        credentials aside — what the transfer it uses cannot carry."""
        if cls.supports_team_transfer(tournament):
            from plugins.ffe.ffe_team_session import FFETeamSession

            return FFETeamSession.upload_unavailable_message(tournament)
        from plugins.ffe.papi_converter import PapiConverter

        return PapiConverter.papi_export_unavailable_message(tournament)

    @classmethod
    def ffe_actions_unavailable_message(cls, tournament: Tournament) -> str | None:
        pd = cls.get_tournament_plugin_data(tournament)
        if cls.supports_team_transfer(tournament):
            if not cls.team_transfer_configured(tournament):
                return _(
                    'FFE group account, competition, division or group not defined.'
                )
        elif not pd.ffe_id and not pd.password:
            return _('FFE certification number and password not defined.')
        elif not pd.ffe_id:
            return _('FFE certification number not defined.')
        elif not pd.password:
            return _('FFE password not defined.')
        return cls.upload_unavailable_message(tournament)

    @staticmethod
    def update_tournament_plugin_data(
        tournament: Tournament,
        plugin_data: 'FfeTournamentPluginData',
    ) -> None:
        tournament.stored_tournament.plugin_data[PLUGIN_NAME] = (
            plugin_data.to_stored_value()
        )
        tournament.plugin_data[PLUGIN_NAME] = plugin_data
        with EventDatabase(tournament.event.uniq_id, write=True) as database:
            database.execute(
                'UPDATE tournament SET plugin_data = '
                f"json_set(plugin_data,'$.{PLUGIN_NAME}', json(?)) WHERE id = ?",
                (json.dumps(plugin_data.to_stored_value()), tournament.id),
            )

    @staticmethod
    def update_event_plugin_data(
        event: Event,
        plugin_data: 'FfeEventPluginData',
    ) -> None:
        event.stored_event.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
        event.plugin_data[PLUGIN_NAME] = plugin_data
        with EventDatabase(event.uniq_id, True) as database:
            database.execute(
                'UPDATE info SET plugin_data = '
                f"json_set(plugin_data,'$.{PLUGIN_NAME}', json(?))",
                (json.dumps(plugin_data.to_stored_value()),),
            )

    @classmethod
    def tournament_url(cls, ffe_id: int) -> str:
        return f'https://echecs.asso.fr/FicheTournoi.aspx?Ref={ffe_id}'

    @classmethod
    def player_url(cls, ffe_id: int) -> str:
        return f'https://echecs.asso.fr/FicheJoueur.aspx?Id={ffe_id}'

    @classmethod
    def team_group_url(cls, tournament: Tournament) -> str | None:
        """The group's page in the site's team module (admin side, the
        group account must be logged in)."""
        from plugins.ffe.ffe_session import FFE_ADMIN_URL

        pd = cls.get_tournament_plugin_data(tournament)
        competition_id = cls.team_competition_id(tournament)
        if not competition_id or not pd.team_division_id or not pd.team_group_id:
            return None
        return (
            f'{FFE_ADMIN_URL}/Equipes.aspx?C={competition_id}'
            f'&D={pd.team_division_id}&G={pd.team_group_id}'
        )

    @classmethod
    def resolve_tournament_upload_statuses(
        cls, tournament: Tournament
    ) -> list[FFEUploadStatus]:
        from plugins.ffe.ffe_background_uploader import FfeBackgroundUploader

        plugin_data = cls.get_tournament_plugin_data(tournament)

        if not cls.is_configured(tournament):
            return [NotConfiguredFFEUploadStatus()]

        statuses: list[FFEUploadStatus] = []

        # Last upload failure
        if plugin_data.upload_failure_id:
            status = FFEUploadFailureStatusManager().get_object(
                plugin_data.upload_failure_id
            )
            statuses.append(status)

        if cls.upload_unavailable_message(tournament):
            statuses.append(IncompatibleFFEUploadStatus())

        is_modified = FfeBackgroundUploader.ffe_upload_needed(tournament)
        # Current data status
        if not plugin_data.last_upload_at:
            statuses.append(NeverUploadedFFEUploadStatus())
        elif is_modified:
            statuses.append(ModifiedFFEUploadStatus())
        else:
            statuses.append(UpToDateFFEUploadStatus())

        # Next upload status
        if FfeBackgroundUploader.is_upload_ongoing(tournament):
            statuses.append(OngoingFFEUploadStatus())
        elif FfeBackgroundUploader.is_upload_queued(tournament) or (
            FfeBackgroundUploader.is_upload_scheduled(tournament) and is_modified
        ):
            statuses.append(PendingFFEUploadStatus())
        return statuses

    @classmethod
    def resolve_period_upload_statuses(
        cls, period: 'TournamentPeriod'
    ) -> list[FFEUploadStatus]:
        """How the submission of one slice stands.

        A slice is submitted under its own registration, so it answers
        for its own upload: whether it has been sent, and how it went.
        What is true of the tournament as a whole — whether its data has
        moved since — belongs to the tournament's own row."""
        from plugins.ffe.ffe_background_uploader import FfeBackgroundUploader

        # What the slice itself holds: borrowing the tournament's would
        # report its upload as this slice's.
        plugin_data = cls.get_period_own_plugin_data(period)
        if not plugin_data.ffe_id or not plugin_data.password:
            return [NotConfiguredFFEUploadStatus()]
        statuses: list[FFEUploadStatus] = []
        if plugin_data.upload_failure_id:
            statuses.append(
                FFEUploadFailureStatusManager().get_object(
                    plugin_data.upload_failure_id
                )
            )
        if not plugin_data.last_upload_at:
            statuses.append(NeverUploadedFFEUploadStatus())
        else:
            statuses.append(UpToDateFFEUploadStatus())
        if FfeBackgroundUploader.is_period_upload_ongoing(period):
            statuses.append(OngoingFFEUploadStatus())
        elif FfeBackgroundUploader.is_period_upload_pending(period):
            statuses.append(PendingFFEUploadStatus())
        return statuses


class FFEUploadFailureStatusManager(EntityManager[FailureFFEUploadStatus]):
    def entity_types(self) -> list[type[FailureFFEUploadStatus]]:
        return [
            NetworkFailureFFEUploadStatus,
            UnexpectedFailureFFEUploadStatus,
            NotReachableFFEUploadStatus,
            AuthFailureFFEUploadStatus,
            FinishedFailureFFEUploadStatus,
            PapiConversionFailureFFEUploadStatus,
            GroupNotFoundFFEUploadStatus,
            RejectedFFEUploadStatus,
        ]


class PlayerFFELicence(StrEnum):
    NONE = ''
    N = 'N'
    B = 'B'
    A = 'A'

    @property
    def name(self) -> str:
        match self:
            case PlayerFFELicence.NONE:
                return _('No FFE Licence')
            case PlayerFFELicence.N:
                return _('Expired FFE licence')
            case PlayerFFELicence.B:
                return _('FFE licence B (leisure)')
            case PlayerFFELicence.A:
                return _('FFE licence A (competition)')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def compact_name(self) -> str:
        match self:
            case PlayerFFELicence.NONE:
                return pgettext('FFE licence', 'None')
            case PlayerFFELicence.N:
                return pgettext('FFE licence', 'N - Expired')
            case PlayerFFELicence.A:
                return pgettext('FFE licence', 'A - Competition')
            case PlayerFFELicence.B:
                return pgettext('FFE licence', 'B - Leisure')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def short_name(self) -> str:
        if self == PlayerFFELicence.NONE:
            return '-'
        return self.value

    @staticmethod
    def validate(string: str) -> bool:
        """Returns True if the string is a correct licence number."""
        return bool(re.match(r'^[A-Z][A-Z\d]\d{4}$', string))

    @property
    def sort_index(self) -> int:
        return _LICENCE_SORT_INDEX[self]


_LICENCE_SORT_INDEX = {
    PlayerFFELicence.NONE: 0,
    PlayerFFELicence.N: 1,
    PlayerFFELicence.B: 2,
    PlayerFFELicence.A: 3,
}


class FFEArbiterTitle(StrEnum):
    NONE = ''
    AS = 'AS'
    AFJ = 'AFJ'
    AFC = 'AFC'
    AFO1 = 'AFO1'
    AFO2 = 'AFO2'
    AFE1 = 'AFE1'
    AFE2 = 'AFE2'

    @classmethod
    def from_html(cls, html_arbiter_string: str) -> 'FFEArbiterTitle':
        match html_arbiter_string:
            case 'Arbitre Jeune':
                return cls.AFJ
            case 'Arbitre Club':
                return cls.AFC
            case 'Arbitre Open 1':
                return cls.AFO1
            case 'Arbitre Open 2':
                return cls.AFO2
            case 'Arbitre Elite 1':
                return cls.AFE1
            case 'Arbitre Elite 2':
                return cls.AFE2
            case _:
                return cls.NONE

    @property
    def name(self) -> str:
        match self:
            case FFEArbiterTitle.NONE:
                return '-'
            case FFEArbiterTitle.AS:
                return _('Trainee Arbiter')
            case FFEArbiterTitle.AFJ:
                return _('Young Arbiter')
            case FFEArbiterTitle.AFC:
                return _('Club Arbiter')
            case FFEArbiterTitle.AFO1:
                return _('Open Arbiter (level 1)')
            case FFEArbiterTitle.AFO2:
                return _('Open Arbiter (level 2)')
            case FFEArbiterTitle.AFE1:
                return _('Elite Arbiter (level 1)')
            case FFEArbiterTitle.AFE2:
                return _('Elite Arbiter (level 2)')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def short_name(self) -> str:
        return self.value


@dataclass
class FfeEventPluginData(PluginData):
    auto_upload: bool = True
    leave_fixed_board_holes: bool = True

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            auto_upload=stored_value.get('auto_upload', False),
            leave_fixed_board_holes=stored_value.get('leave_fixed_board_holes', True),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'auto_upload': self.auto_upload,
            'leave_fixed_board_holes': self.leave_fixed_board_holes,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        if 'ffe_event_fields' in data:
            leave_fixed_board_holes = WebContext.form_data_to_bool(
                data, 'ffe_leave_fixed_board_holes'
            )
        elif previous_object is not None:
            leave_fixed_board_holes = previous_object.leave_fixed_board_holes
        else:
            leave_fixed_board_holes = True
        plugin_data = cls(leave_fixed_board_holes=leave_fixed_board_holes)
        if previous_object:
            plugin_data.auto_upload = previous_object.auto_upload
        return plugin_data

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'ffe_leave_fixed_board_holes': self.leave_fixed_board_holes,
            }
        )


@dataclass
class FfeTournamentPluginData(PluginData):
    ffe_id: int | None = None
    password: str | None = None
    # Team competitions are sent through the site's team module, with a
    # group account rather than a tournament certification number.
    team_login: str | None = None
    team_password: str | None = None
    team_competition_id: int | None = None
    team_competition_name: str | None = None
    team_division_id: int | None = None
    team_division_name: str | None = None
    team_group_id: int | None = None
    team_group_name: str | None = None
    auto_upload: bool = False
    last_upload_at: datetime | None = None
    last_upload_attempt_at: datetime | None = None
    upload_failure_id: str | None = None
    # What the site or the upload said, when the failure has a text.
    upload_failure_message: str | None = None

    @property
    def last_upload_at_str(self) -> str:
        if not self.last_upload_at:
            return '-'
        return format_datetime(self.last_upload_at)

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            ffe_id=stored_value.get('ffe_id'),
            password=stored_value.get('password'),
            team_login=stored_value.get('team_login'),
            team_password=stored_value.get('team_password'),
            team_competition_id=stored_value.get('team_competition_id'),
            team_competition_name=stored_value.get('team_competition_name'),
            team_division_id=stored_value.get('team_division_id'),
            team_division_name=stored_value.get('team_division_name'),
            team_group_id=stored_value.get('team_group_id'),
            team_group_name=stored_value.get('team_group_name'),
            auto_upload=stored_value.get('auto_upload', False),
            last_upload_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_upload')
            ),
            last_upload_attempt_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_upload_attempt_at')
            ),
            upload_failure_id=stored_value.get('upload_failure_id'),
            upload_failure_message=stored_value.get('upload_failure_message'),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'ffe_id': self.ffe_id,
            'password': self.password,
            'team_login': self.team_login,
            'team_password': self.team_password,
            'team_competition_id': self.team_competition_id,
            'team_competition_name': self.team_competition_name,
            'team_division_id': self.team_division_id,
            'team_division_name': self.team_division_name,
            'team_group_id': self.team_group_id,
            'team_group_name': self.team_group_name,
            'auto_upload': self.auto_upload,
            'last_upload': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.last_upload_at
            ),
            'last_upload_attempt_at': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.last_upload_attempt_at
            ),
            'upload_failure_id': self.upload_failure_id,
            'upload_failure_message': self.upload_failure_message,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        plugin_data = cls(
            ffe_id=WebContext.form_data_to_int(data, 'ffe_id'),
            password=WebContext.form_data_to_str(data, 'ffe_password'),
            team_login=WebContext.form_data_to_str(data, 'ffe_team_login'),
            team_password=WebContext.form_data_to_str(data, 'ffe_team_password'),
        )
        # The competition, division and group selects carry ``id|name``:
        # the name is what the arbiter sees afterwards, the id what the
        # upload uses.
        plugin_data.team_competition_id, plugin_data.team_competition_name = (
            cls._split_site_choice(
                WebContext.form_data_to_str(data, 'ffe_team_competition')
            )
        )
        plugin_data.team_division_id, plugin_data.team_division_name = (
            cls._split_site_choice(
                WebContext.form_data_to_str(data, 'ffe_team_division')
            )
        )
        plugin_data.team_group_id, plugin_data.team_group_name = cls._split_site_choice(
            WebContext.form_data_to_str(data, 'ffe_team_group')
        )
        if previous_object:
            if action != 'clone' and (
                (plugin_data.ffe_id and plugin_data.password)
                or plugin_data.team_place_configured
            ):
                plugin_data.last_upload_at = previous_object.last_upload_at
                plugin_data.last_upload_attempt_at = (
                    previous_object.last_upload_attempt_at
                )
                plugin_data.upload_failure_id = previous_object.upload_failure_id
                plugin_data.upload_failure_message = (
                    previous_object.upload_failure_message
                )
            plugin_data.auto_upload = previous_object.auto_upload
        return plugin_data

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'ffe_id': self.ffe_id if action != 'clone' else '',
                'ffe_password': self.password if action != 'clone' else '',
                'ffe_team_login': self.team_login if action != 'clone' else '',
                'ffe_team_password': self.team_password if action != 'clone' else '',
                'ffe_team_competition': self.site_choice(
                    self.team_competition_id, self.team_competition_name
                ),
                'ffe_team_division': self.site_choice(
                    self.team_division_id, self.team_division_name
                ),
                'ffe_team_group': self.site_choice(
                    self.team_group_id, self.team_group_name
                ),
            }
        )

    @staticmethod
    def site_choice(id_: int | None, name: str | None) -> str:
        """The ``id|name`` value of a site select option."""
        return f'{id_}|{name}' if id_ else ''

    @staticmethod
    def _split_site_choice(value: str | None) -> tuple[int | None, str | None]:
        if not value or '|' not in value:
            return None, None
        id_str, name = value.split('|', 1)
        try:
            return int(id_str), name
        except ValueError:
            return None, None

    @property
    def team_place_configured(self) -> bool:
        """Whether the group the match reports go to, and the account
        that may write them, are named. The competition is left out: a
        rule set that names one does not store it."""
        return bool(
            self.team_login
            and self.team_password
            and self.team_division_id
            and self.team_group_id
        )


@dataclass
class FfePlayerPluginData(PluginData):
    ffe_id: int | None
    ffe_licence: PlayerFFELicence
    ffe_licence_number: str | None
    league: str | None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        ffe_licence_number = stored_value.get('ffe_licence_number')
        return cls(
            ffe_id=stored_value.get('ffe_id'),
            ffe_licence=PlayerFFELicence(
                stored_value.get('ffe_licence', PlayerFFELicence.NONE)
                if ffe_licence_number
                else PlayerFFELicence.NONE
            ),
            ffe_licence_number=ffe_licence_number,
            league=stored_value.get('league'),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'ffe_id': self.ffe_id,
            'ffe_licence': (
                self.ffe_licence if self.ffe_licence_number else PlayerFFELicence.NONE
            ).value,
            'ffe_licence_number': self.ffe_licence_number,
            'league': self.league,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        return cls(
            ffe_id=WebContext.form_data_to_int(data, 'ffe_id'),
            ffe_licence=PlayerFFELicence(
                WebContext.form_data_to_str(data, 'ffe_licence')
                or PlayerFFELicence.NONE
            ),
            ffe_licence_number=WebContext.form_data_to_str(data, 'ffe_licence_number'),
            league=WebContext.form_data_to_str(data, 'ffe_league'),
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        if action == FormAction.REPLACE:
            return {}
        return WebContext.values_dict_to_form_data(
            {
                'ffe_id': self.ffe_id,
                'ffe_licence': self.ffe_licence.value,
                'ffe_licence_number': self.ffe_licence_number,
                'ffe_league': self.league,
            }
        )


@dataclass
class FfeAccountPluginData(AccountPluginData):
    ffe_licence_number: str | None
    ffe_arbiter_title: FFEArbiterTitle

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            ffe_licence_number=stored_value.get('ffe_licence_number'),
            ffe_arbiter_title=FFEArbiterTitle(
                stored_value.get('ffe_arbiter_title', FFEArbiterTitle.NONE)
            ),
        )

    @classmethod
    def from_stored_player(cls, stored_player: StoredPlayer) -> Self:
        return cls(
            ffe_licence_number=stored_player.plugin_data.get(PLUGIN_NAME, {}).get(
                'ffe_licence_number', None
            ),
            ffe_arbiter_title=FFEArbiterTitle(
                stored_player.transient_arbiter_titles.get('ffe')
                or FFEArbiterTitle.NONE
            ),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'ffe_arbiter_title': self.ffe_arbiter_title.value,
            'ffe_licence_number': self.ffe_licence_number,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        return cls(
            ffe_licence_number=WebContext.form_data_to_str(data, 'ffe_licence_number'),
            ffe_arbiter_title=FFEArbiterTitle(
                WebContext.form_data_to_str(data, 'ffe_arbiter_title')
                or FFEArbiterTitle.NONE
            ),
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'ffe_licence_number': self.ffe_licence_number,
                'ffe_arbiter_title': self.ffe_arbiter_title.value,
            }
        )
