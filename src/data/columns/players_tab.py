from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any, Counter, Callable

from common.i18n import _
from common.i18n.utils import normalized_key
from data.event import Event
from data.player import Player
from data.player_categories import PlayerCategory
from data.tournament import Tournament
from utils.entity import IdentifiableEntity
from utils.enum import CheckInStatus, PlayerGender
from .column import Column


@dataclass
class ColumnFilterValue:
    key: str
    value: Any
    count: int
    is_active: bool


class PlayersTabColumn(Column[Player], IdentifiableEntity, ABC):
    """Base class for columns of the players tab."""

    def __init__(self):
        # Stored states of the column
        self.is_visible: bool | None = None
        self.is_enabled: bool | None = None
        self.filter_values: list[ColumnFilterValue] = []

        # Overridable by plugins
        self.sort_key_function: Callable[[Player], tuple] = self._get_sort_key
        self.is_default_visible = True

    @property
    def header_button_template(self) -> str | None:
        """Template for a button added to the header, not conflicting with the sort."""
        return None

    @property
    def is_hideable(self) -> bool:
        """Defines if the column can be hidden."""
        return True

    @property
    def is_compact(self) -> bool:
        """Defines if the display of the column should be compact."""
        return False

    @property
    def align_start(self) -> bool:
        """Defines if the header and cell content should be aligned left (centered otherwise)."""
        return False

    @property
    def shared_classes(self) -> str:
        return 'text-nowrap'

    @property
    def header_content(self) -> str:
        return self.name

    @property
    def is_tournament_column(self) -> bool:
        """Defines if the column only in usable in a single tournament context."""
        return False

    def is_enabled_for_players(self, players: list[Player]) -> bool:
        """Defines if the column is enabled for the given players.
        Disabled columns do not appear in the interface.
        If this can be determined at tournament level,
        use is_enabled_for_tournaments instead."""
        return True

    def is_enabled_for_tournaments(self, tournaments: list[Tournament]) -> bool:
        """Defines if the column is enabled for the given tournaments."""
        return True

    @abstractmethod
    def _get_sort_key(self, player: Player) -> tuple:
        """Get the sort key from a player to sort by this column.
        After the values of this key the players are sorted by name."""

    @property
    def swap_asc_desc_icon(self) -> bool:
        """Defines if the first sort icon to appear is the asc sort."""
        return False

    @property
    def is_searchable(self) -> bool:
        """Defines if the column can be searched from the global search bar."""
        return False

    def get_search_key(self, player: Player) -> str:
        """Get the key that the search should match for the player to be filtered in."""
        raise NotImplementedError('Required if is_searchable=True')

    # -------------------------------------------------------------------------
    # Filter
    # -------------------------------------------------------------------------

    @property
    def is_filtrable(self) -> bool:
        """Defines if the rows can be filtered by this column."""
        return False

    def get_filter_key(self, player: Player) -> str:
        """Get from a player the key used to gather them in the filters."""
        raise NotImplementedError('Required if is_filtrable=True')

    @property
    def filter_row_template(self) -> str:
        """Path of the template describing the content of the row of the filter.
        The template takes as input the variable `filter_value`."""
        return ''

    def get_filter_row_content(self, value: Any) -> str:
        """Get the content of a filter row from the value."""
        return value

    def get_filter_row_tooltip(self, value: Any) -> str:
        """Get the of a filter row from the value."""
        return ''

    def get_filter_value_from_key(self, filter_key: str, event: Event) -> Any:
        """Get a value from the key of a filter.
        This value is passed to the filter row template.
        Raise a ValueError if the value is not a valid form key."""
        return filter_key

    @property
    def filter_mandatory_keys(self) -> list[str]:
        """Get a list of keys that will be included in the
        filter event if no player matches that key."""
        return []

    def get_filter_value_sort_key(self, filter_value: ColumnFilterValue) -> Any:
        return normalized_key(filter_value.key)

    def set_filter_values(
        self, players: list[Player], event: Event, active_keys: list[str]
    ):
        count_by_key: Counter[str] = Counter[str]()
        for key in self.filter_mandatory_keys:
            count_by_key[key] = 0
        for player in players:
            count_by_key[self.get_filter_key(player)] += 1

        filter_values = [
            ColumnFilterValue(
                key=key,
                value=self.get_filter_value_from_key(key, event),
                count=count,
                is_active=key in active_keys,
            )
            for key, count in count_by_key.items()
        ]
        self.filter_values = sorted(filter_values, key=self.get_filter_value_sort_key)

    @property
    def has_active_filter_value(self) -> bool:
        return any(filter_value.is_active for filter_value in self.filter_values)

    @property
    def all_filter_value_active(self) -> bool:
        return all(filter_value.is_active for filter_value in self.filter_values)


class FilterPlayersTabColumn(PlayersTabColumn, ABC):
    @property
    def is_filtrable(self) -> bool:
        return True

    @abstractmethod
    def get_filter_key(self, player: Player) -> str: ...


class NamePlayersTabColumn(FilterPlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return 'name'

    @staticmethod
    def static_name() -> str:
        return _('Name')

    def _get_sort_key(self, player: Player) -> tuple:
        return tuple()

    @property
    def is_hideable(self) -> bool:
        return False

    @property
    def align_start(self) -> bool:
        return True

    @property
    def shared_classes(self) -> str:
        return 'text-nowrap position-sticky table-sticky-border z-1 w-15em'

    @property
    def cell_template(self) -> str | None:
        return 'cells/name.html'

    @property
    def is_searchable(self) -> bool:
        return True

    def get_search_key(self, player: Player) -> str:
        return f'{player.last_name} {player.first_name}'

    def get_filter_key(self, player: Player) -> str:
        tournament_player = player.optional_single_tournament_player
        if tournament_player is None or tournament_player.matches_tournament_criteria:
            return 'match'
        return 'no-match'

    @property
    def filter_row_template(self) -> str:
        return 'filter_rows/name.html'

    def get_filter_row_tooltip(self, value: Any) -> str:
        if value == 'match':
            return _('Players which match the criteria of their tournament.')
        return _('Players which do not match the criteria of their tournament.')


class CheckInPlayersTabColumn(FilterPlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return 'check_in'

    @staticmethod
    def static_name() -> str:
        return _('Check-in')

    @property
    def is_hideable(self) -> bool:
        return False

    @property
    def header_template(self) -> str:
        return 'headers/check_in.html'

    @property
    def cell_template(self) -> str | None:
        return 'cells/check_in.html'

    @property
    def filter_row_template(self) -> str:
        return 'filter_rows/check_in.html'

    def _get_sort_key(self, player: Player) -> tuple:
        tp = player.optional_single_tournament_player
        return (tp.check_in_status if tp is not None else CheckInStatus.ABSENT,)

    @property
    def is_tournament_column(self) -> bool:
        return True

    def get_filter_key(self, player: Player) -> str:
        tp = player.optional_single_tournament_player
        if tp is None:
            return str(CheckInStatus.ABSENT.value)
        return str(tp.check_in_status.value)

    def get_filter_value_from_key(self, filter_key: str, event: Event) -> Any:
        return CheckInStatus(int(filter_key))

    def get_filter_value_sort_key(self, filter_value: ColumnFilterValue) -> Any:
        return filter_value.value

    @property
    def filter_mandatory_keys(self) -> list[str]:
        return [
            str(status.value)
            for status in (CheckInStatus.ABSENT, CheckInStatus.PRESENT)
        ]

    def get_filter_row_tooltip(self, value: Any) -> str:
        return CheckInStatus(int(value)).description

    def is_enabled_for_tournaments(self, tournaments: list[Tournament]) -> bool:
        if tournaments and tournaments[0].event.is_team_event:
            return False
        return True


class RatingPlayersTabColumn(PlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return 'rating'

    @staticmethod
    def static_name() -> str:
        return _('Elo *** ELO RATING')

    @property
    def is_tournament_column(self) -> bool:
        # Not gated on tournament membership: players without a
        # tournament show their event-default rating (see the cell
        # template).
        return False

    def _get_sort_key(self, player: Player) -> tuple:
        tp = player.optional_single_tournament_player
        rating = tp.rating if tp is not None else (player.event_default_rating or 0)
        return -rating, -player.title.sort_index

    @property
    def swap_asc_desc_icon(self) -> bool:
        return True

    @property
    def cell_template(self) -> str | None:
        return 'cells/rating.html'

    @property
    def is_hideable(self) -> bool:
        return False


class FederationPlayersTabColumn(FilterPlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return 'federation'

    @staticmethod
    def static_name() -> str:
        return _('Federation')

    @property
    def is_compact(self) -> bool:
        return True

    @property
    def header_template(self) -> str:
        return 'headers/federation.html'

    @property
    def cell_template(self) -> str | None:
        return 'cells/federation.html'

    def _get_sort_key(self, player: Player) -> tuple:
        return (player.federation.name,)

    def get_filter_key(self, player: Player) -> str:
        return player.federation.name

    @property
    def filter_row_template(self) -> str:
        return 'filter_rows/federation.html'


class ClubPlayersTabColumn(FilterPlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return 'club'

    @staticmethod
    def static_name() -> str:
        return _('Club')

    def get_filter_key(self, player: Player) -> str:
        return player.club.name or '-'

    @property
    def is_compact(self) -> bool:
        return True

    @property
    def align_start(self) -> bool:
        return True

    def get_cell_classes(self, player: Player) -> str:
        return 'text-truncate mw-15em'

    def get_cell_content(self, player: Player) -> Any:
        return player.club.name

    def _get_sort_key(self, player: Player) -> tuple:
        return (
            not player.club.name,
            player.federation.name,
            player.club.name,
        )

    @property
    def is_searchable(self) -> bool:
        return True

    def get_search_key(self, player: Player) -> str:
        return player.club.name


class DateOfBirthPlayersTabColumn(PlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return 'date_of_birth'

    @staticmethod
    def static_name() -> str:
        return _('Date of birth')

    @property
    def header_template(self) -> str:
        return 'headers/date_of_birth.html'

    @property
    def cell_template(self) -> str | None:
        return 'cells/date_of_birth.html'

    def _get_sort_key(self, player: Player) -> tuple:
        if not (dob := player.date_of_birth):
            dob = date(player.year_of_birth or date.today().year, 12, 31)
        return (dob - date.today(),)


class CategoryPlayersTabColumn(FilterPlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return 'category'

    @staticmethod
    def static_name() -> str:
        return _('Category')

    @property
    def header_template(self) -> str:
        return 'headers/category.html'

    def get_cell_content(self, player: Player) -> Any:
        return player.category.name

    def get_filter_key(self, player: Player) -> str:
        return player.category.id

    def get_filter_value_from_key(self, filter_key: str, event: Event) -> Any:
        return PlayerCategory.from_id(filter_key)

    def _get_sort_key(self, player: Player) -> tuple:
        if not (dob := player.date_of_birth):
            dob = date(player.year_of_birth or 1900, 1, 1)
        return (date.today() - dob,)

    def get_filter_row_content(self, value: Any) -> str:
        return value.name

    def get_filter_value_sort_key(self, filter_value: ColumnFilterValue) -> Any:
        return filter_value.value


class MailPlayersTabColumn(PlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return 'mail'

    @staticmethod
    def static_name() -> str:
        return _('Email address')

    @property
    def header_template(self) -> str | None:
        return 'headers/mail.html'

    @property
    def is_compact(self) -> bool:
        return True

    @property
    def cell_template(self) -> str | None:
        return 'cells/mail.html'

    def _get_sort_key(self, player: Player) -> tuple:
        return not bool(player.mail), player.mail or ''

    def is_enabled_for_players(self, players: list[Player]) -> bool:
        return any(player.mail for player in players)


class PhonePlayersTabColumn(PlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return 'phone'

    @staticmethod
    def static_name() -> str:
        return _('Phone')

    @property
    def header_template(self) -> str | None:
        return 'headers/phone.html'

    @property
    def is_compact(self) -> bool:
        return True

    @property
    def cell_template(self) -> str | None:
        return 'cells/phone.html'

    def _get_sort_key(self, player: Player) -> tuple:
        return not bool(player.phone), player.phone or ''

    def is_enabled_for_players(self, players: list[Player]) -> bool:
        return any(player.phone for player in players)


class GenderPlayersTabColumn(FilterPlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return 'gender'

    @staticmethod
    def static_name() -> str:
        return _('Gender')

    @property
    def header_template(self) -> str | None:
        return 'headers/gender.html'

    def get_cell_content(self, player: Player) -> Any:
        return player.gender.short_name

    def _get_sort_key(self, player: Player) -> tuple:
        return (player.gender,)

    def get_filter_key(self, player: Player) -> str:
        return player.gender.value

    def get_filter_value_from_key(self, filter_key: str, event: Event) -> Any:
        return PlayerGender(filter_key)

    def get_filter_row_content(self, value: Any) -> str:
        return value.name


class FixedPlayersTabColumn(PlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return 'fixed'

    @staticmethod
    def static_name() -> str:
        return _('Fixed board')

    @property
    def header_template(self) -> str | None:
        return 'headers/fixed.html'

    def get_cell_content(self, player: Player) -> Any:
        return player.fixed or ''

    @property
    def is_compact(self) -> bool:
        return True

    def _get_sort_key(self, player: Player) -> tuple:
        return not bool(player.fixed), player.fixed or 0

    def is_enabled_for_players(self, players: list[Player]) -> bool:
        return any(player.fixed for player in players)


class FideIdPlayersTabColumn(PlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return 'fide_id'

    @staticmethod
    def static_name() -> str:
        return _('FIDE ID')

    @property
    def header_template(self) -> str:
        return 'headers/fide_id.html'

    @property
    def cell_template(self) -> str | None:
        return 'cells/fide_id.html'

    @property
    def is_compact(self) -> bool:
        return True

    def _get_sort_key(self, player: Player) -> tuple:
        return (not bool(player.fide_id),)

    def is_enabled_for_players(self, players: list[Player]) -> bool:
        return any(player.fide_id for player in players)


class PaymentPlayersTabColumn(PlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return 'payment'

    @staticmethod
    def static_name() -> str:
        return _('Payment')

    @property
    def is_compact(self) -> bool:
        return True

    @property
    def header_template(self) -> str | None:
        return 'headers/payment.html'

    @staticmethod
    def _format_float(value: float) -> str:
        return str(int(value)) if value.is_integer() else f'{value:.2f}'

    def get_cell_content(self, player: Player) -> Any:
        if player.owed:
            paid = self._format_float(player.paid)
            owed = self._format_float(player.owed)
            return f'{paid}/{owed}'
        if player.paid:
            return self._format_float(player.paid)
        return ''

    def is_enabled_for_players(self, players: list[Player]) -> bool:
        return any(player.owed or player.paid for player in players)

    def _get_sort_key(self, player: Player) -> tuple:
        return (
            not bool(player.owed),
            player.paid >= player.owed,
            player.paid,
        )


class TournamentPlayersTabColumn(FilterPlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return 'tournament'

    @staticmethod
    def static_name() -> str:
        return _('Tournament')

    @property
    def align_start(self) -> bool:
        return True

    @property
    def cell_template(self) -> str | None:
        return 'cells/tournament.html'

    @property
    def is_tournament_column(self) -> bool:
        return True

    def get_filter_key(self, player: Player) -> str:
        return str(player.single_tournament.id)

    def get_filter_value_from_key(self, filter_key: str, event: Event) -> Any:
        return event.tournaments_by_id[int(filter_key)]

    def get_filter_row_content(self, value: Any) -> str:
        return value.name

    def get_filter_value_sort_key(self, filter_value: ColumnFilterValue) -> Any:
        return filter_value.value.index

    def _get_sort_key(self, player: Player) -> tuple:
        return (player.single_tournament.index,)

    def is_enabled_for_tournaments(self, tournaments: list[Tournament]) -> bool:
        if tournaments and tournaments[0].event.is_team_event:
            return False
        return len(tournaments) > 1


class TeamPlayersTabColumn(FilterPlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return 'team'

    @staticmethod
    def static_name() -> str:
        return _('Team')

    @property
    def align_start(self) -> bool:
        return True

    @property
    def cell_template(self) -> str | None:
        return 'cells/team.html'

    def get_filter_key(self, player: Player) -> str:
        return str(player.team_id) if player.team_id else ''

    def get_filter_value_from_key(self, filter_key: str, event: Event) -> Any:
        if not filter_key:
            return None
        return event.teams_by_id.get(int(filter_key))

    def get_filter_row_content(self, value: Any) -> str:
        return value.name if value is not None else '-'

    def get_filter_value_sort_key(self, filter_value: ColumnFilterValue) -> Any:
        if filter_value.value is None:
            return ('', '')
        return (filter_value.value.name.lower(), str(filter_value.value.id))

    def _get_sort_key(self, player: Player) -> tuple:
        team = player.team
        return (team.name.lower() if team is not None else '~~~',)

    def is_enabled_for_tournaments(self, tournaments: list[Tournament]) -> bool:
        return bool(tournaments and tournaments[0].event.is_team_event)


class CommentPlayersTabColumn(PlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return 'comment'

    @staticmethod
    def static_name() -> str:
        return _('Comment')

    @property
    def align_start(self) -> bool:
        return True

    @property
    def header_template(self) -> str | None:
        return 'headers/comment.html'

    def get_cell_content(self, player: Player) -> Any:
        return player.comment or ''

    def is_enabled_for_players(self, players: list[Player]) -> bool:
        return any(player.comment for player in players)

    def _get_sort_key(self, player: Player) -> tuple:
        return not bool(player.comment), player.comment or ''


class RecordPlayersTabColumn(PlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return 'record'

    @staticmethod
    def static_name() -> str:
        return _('Record')

    @property
    def is_tournament_column(self) -> bool:
        return True

    @property
    def align_start(self) -> bool:
        return True

    @property
    def shared_classes(self) -> str:
        return 'text-nowrap pe-2'

    @property
    def header_template(self) -> str | None:
        return 'headers/record.html'

    @property
    def cell_template(self) -> str | None:
        return 'cells/record.html'

    def _get_sort_key(self, player: Player) -> tuple:
        tp = player.optional_single_tournament_player
        if tp is None:
            return 0.0, 0
        played = 0
        points = 0.0
        for pairing in tp.pairings.values():
            played += pairing.played
            points += pairing.points
        return points, played
