import base64
import weakref
from contextlib import suppress
from dataclasses import dataclass
from datetime import date
from functools import total_ordering, cached_property
from logging import Logger
from typing import TYPE_CHECKING, Any, Self, Callable, SupportsFloat
from trf import Player as TrfPlayer

from common.i18n import _
from common.logger import get_logger
from data.pairing import Pairing
from data.util import (
    PlayerGender,
    PlayerTitle,
    BoardColor,
    Result,
    TournamentRating,
    PlayerRatingType,
    PlayerCategory,
)

if TYPE_CHECKING:
    from _weakref import ReferenceType
    from data.tournament import Tournament

logger: Logger = get_logger()


@dataclass(frozen=True)
@total_ordering
class Federation:
    name: str = ''

    @cached_property
    def to_query_param(self) -> str:
        return base64.b64encode(self.name.encode('utf-8')).decode('utf-8')

    @classmethod
    def from_query_param(cls, query_param: str) -> Self:
        return base64.b64decode(query_param).decode('utf-8')

    def __le__(self, other: Self):
        # p1 <= p2 calls p1.__le__(p2)
        assert isinstance(other, self.__class__), (
            f'Can not compare [{type(other)}] and [{self.__class__}]'
        )
        return self.name <= other.name

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
@total_ordering
class Club:
    name: str = ''

    @cached_property
    def to_query_param(self) -> str:
        return base64.b64encode(self.name.encode('utf-8')).decode('utf-8')

    @classmethod
    def from_query_param(cls, query_param: str) -> Self:
        return base64.b64decode(query_param).decode('utf-8')

    def __le__(self, other: Self):
        # p1 <= p2 calls p1.__le__(p2)
        assert isinstance(other, self.__class__), (
            f'Can not compare [{type(other)}] and [{self.__class__}]'
        )
        return self.name <= other.name

    def __str__(self) -> str:
        return self.name


class TournamentPlayer:
    """A class representing a player in a tournament"""
    def __init__(
        self,
        id: int | None,
        last_name: str,
        first_name: str | None,
        date_of_birth: date | None,
        gender: PlayerGender,
        fide_id: int | None,
        federation: Federation,
        title: PlayerTitle,
        pairings: dict[int, Pairing],
        estimation: int | None = None,
        point_values: dict[Result, float] | None = None,
        tournament: 'Tournament | None' = None,
    ):
        self.id: int | None = id
        self.last_name: str = last_name
        self.first_name: str | None = first_name
        self.date_of_birth: date | None = date_of_birth
        self.gender: PlayerGender = gender
        self.fide_id: int | None = fide_id
        self.federation: Federation = federation
        self.title: PlayerTitle = title
        self._estimation: int | None = estimation
        self.pairings: dict[int, Pairing] = pairings
        self._point_values: dict[Result, float] = point_values
        self._tournament_ref: 'ReferenceType[Tournament] | None' = None
        self.tournament: 'Tournament | None' = tournament

    @property
    def tournament(self) -> 'Tournament | None':
        return self._tournament_ref() if self._tournament_ref else None

    @tournament.setter
    def tournament(self, tournament: 'Tournament | None'):
        self._tournament_ref = weakref.ref(tournament) if tournament else None

    @property
    def point_values(self) -> dict[Result, float] | None:
        return self._point_values

    def points_before_round(self, round_: int, only_played: bool = False) -> float:
        # NOTE(Amaras) this does not rely on the fact that insertion order
        # is preserved in 3.6+ dict, because I can't be sure insertion order
        # is the correct (increasing) round order
        # NOTE(Amaras) if you were to include the current round
        # in the computation, boards regularly change their ordering
        # during the current round as results are added
        return sum(
            pairing.result.points(self.point_values)
            for round_index, pairing in self.pairings.items()
            if round_index < round_ and
            (pairing.played or not only_played)
        )

    def points_after_round(self, round_: int, only_played: bool = False) -> float:
        # NOTE(Amaras) this does not rely on the fact that insertion order
        # is preserved in 3.6+ dict, because I can't be sure insertion order
        # is the correct (increasing) round order
        # NOTE(Amaras) if you were to include the current round
        # in the computation, boards regularly change their ordering
        # during the current round as results are added
        return sum(
            pairing.result.points(self.point_values)
            for round_index, pairing in self.pairings.items()
            if round_index <= round_ and
            (pairing.played or not only_played)
        )

    def total_points(self, only_played: bool = False) -> float:
        return sum(
            pairing.result.points(self.point_values)
            for pairing in self.pairings.values()
            if pairing.played or not only_played
        )

    @property
    def estimation(self):
        return self._estimation or 0


@total_ordering
class Player(TournamentPlayer):
    """A class representing a player in papi-web."""

    def __init__(
        self,
        id: int,
        last_name: str,
        first_name: str,
        date_of_birth: date | None,
        gender: PlayerGender,
        fide_id: int | None,
        federation: Federation,
        title: PlayerTitle,
        pairings: dict[int, Pairing],

        # Extra fields
        mail: str,
        phone: str,
        comment: str,
        owed: float,
        paid: float,
        ratings: dict[TournamentRating, int],
        rating_types: dict[TournamentRating, PlayerRatingType],
        club: Club,
        fixed: int,
        check_in: bool,
        tournament: 'Tournament | None' = None,
        errors: dict[str, str] | None = None,

        # Plugins can add their own player data
        plugin_data: dict[str, dict[str, Any]] | None = None
    ):
        super().__init__(
            id,
            last_name,
            first_name,
            date_of_birth,
            gender,
            fide_id,
            federation,
            title,
            pairings,
            tournament=tournament,
        )
        self.mail: str = mail
        self.phone: str = phone
        self.comment: str = comment
        self.owed: float = owed
        self.paid: float = paid
        self.ratings: dict[TournamentRating, int] = ratings
        self.rating_types: dict[TournamentRating, PlayerRatingType] = rating_types
        self.federation: Federation = federation
        self.club: Club = club
        self.fixed: int = fixed
        self.check_in: bool = check_in
        self.points: float | None = None
        self.vpoints: float | None = None
        self.board_id: int | None = None
        self.board_number: int | None = None
        self.color: BoardColor | None = None
        self.illegal_moves: int = 0
        self._tie_break_values: list[int | float] | None = None
        self._rank: int | None = None
        self.time_control_initial_time: int | None = None
        self.time_control_increment: int | None = None
        self.time_control_modified: bool | None = None
        self.errors: dict[str, str] = errors or {}
        self.plugin_data: dict[str, dict[str, Any]] = plugin_data or {}

    @staticmethod
    def player_papi_web_id_from_papi_id(tournament_id: int, ref_id: int) -> int:
        return tournament_id * 10000 + ref_id

    @staticmethod
    def player_papi_id_from_papi_web_id(player_id: int) -> int:
        return player_id % 10000

    @staticmethod
    def player_tournament_id_from_papi_web_id(player_id: int) -> int:
        return player_id // 10000

    @property
    def ref_id(self) -> int:
        """Returns the Unique ID of the player in the Papi file (needed while using the Papi storage)."""
        return self.player_papi_id_from_papi_web_id(self.id)

    @property
    def tournament_id(self) -> int:
        return self.player_tournament_id_from_papi_web_id(self.id)

    @property
    def estimation(self) -> int:
        if not self.estimated:
            return self.ratings[self.tournament.rating]
        return self._estimation or 0

    @estimation.setter
    def estimation(self, value: int):
        if not self.estimated:
            self._estimation = self.ratings[self.tournament.rating]
        else:
            self._estimation = value

    @property
    def estimated(self) -> bool:
        return self.rating_types[self.tournament.rating] == PlayerRatingType.ESTIMATED

    @property
    def year_of_birth(self) -> int:
        return self.date_of_birth.year if self.date_of_birth else 0

    @cached_property
    def category(self) -> PlayerCategory:
        return PlayerCategory.from_year_of_birth(self.year_of_birth)

    @property
    def rating(self) -> int:
        return self.ratings[self.tournament.rating]

    @property
    def rating_type(self) -> PlayerRatingType:
        return self.rating_types[self.tournament.rating]

    @property
    def point_values(self) -> dict[Result, float] | None:
        return self.tournament.point_values if self.tournament else None

    def compute_points_before_round(self, before_round: int):
        """Computes and stores the points scored by the player before round `before_round` (returns None)"""
        self.points = self.points_before_round(before_round)

    def points_total(self) -> float:
        return sum(pairing.result.points(self.point_values) for pairing in self.pairings.values())

    @staticmethod
    def _points_str(points: float | None) -> str:
        if points is None:
            return ''
        if points == 0.5:
            return '½'
        return f'{points:.1f}'.replace('.0', '').replace('.5', '½')

    def add_points(self, points: float):
        """If `self.points` is set, add `points` to it.
        Otherwise, leave `self.points` as None."""
        with suppress(TypeError):
            self.points += points

    def to_trf_after_round(
        self,
        player_id_to_trf_id: Callable[[int], int],
        round_: int,
    ) -> TrfPlayer:
        return TrfPlayer(
            startrank=player_id_to_trf_id(self.id),
            name=f'{self.last_name}, {self.first_name}',
            sex=self.gender.to_trf,
            title=self.title.to_trf,
            rating=self.rating,
            fed=self.federation.name,
            id=self.fide_id,
            birthdate=self.date_of_birth.strftime('%Y/%m/%d')
            if self.date_of_birth
            else '',
            points=self.points_after_round(round_),
            rank=self.rank,
            games=[
                result.to_trf(round_nb, player_id_to_trf_id)
                for round_nb, result in self.pairings.items()
                if round_nb <= round_
            ],
        )

    @property
    def points_str(self) -> str:
        return self._points_str(self.points)

    def add_vpoints(self, vpoints: float):
        """If `self.vpoints` is set, add `vpoints` to it.
        Otherwise, leave `self.vpoints` as None."""
        with suppress(TypeError):
            self.vpoints += vpoints

    @property
    def vpoints_str(self) -> str:
        return self._points_str(self.vpoints)

    @property
    def not_paired_str(self) -> str:
        return (
            _('Unpaired *** FEMALE')
            if self.gender == PlayerGender.FEMALE
            else _('Unpaired *** MALE')
        )

    @property
    def exempt_str(self) -> str:
        return (
            _('Exempt *** FEMALE')
            if self.gender == PlayerGender.FEMALE
            else _('Exempt *** MALE')
        )

    def set_board(self, board_id: int, board_number: int, color: BoardColor):
        self.board_id = board_id
        self.board_number = board_number
        self.color = color

    @cached_property
    def has_real_pairings(self) -> bool:
        """Returns True if the player has already been paired with an opponent
        (i.e. can not be deleted from the tournament anymore)."""
        for pairing in self.pairings.values():
            if (
                pairing.opponent_id is not None
                and self.player_papi_id_from_papi_web_id(pairing.opponent_id) > 1
            ):
                return True
        return False

    @cached_property
    def can_check_in_out(self) -> bool:
        """Returns True if the player can check-in/out, i.e. it is not forfeit for the next round."""
        if self.tournament.finished:
            return False
        if self.tournament.playing:
            return False
        if not self.tournament.check_in_open:
            return False
        pairing: Pairing = self.pairings[self.tournament.current_round + 1]
        return (
            not pairing.forfeit
            and not pairing.half_point_bye
            and not pairing.full_point_bye
        )

    @property
    def color_str(self) -> str:
        if self.color is None:
            return ''
        else:
            return str(self.color)

    @property
    def time_control_initial_time_minutes(self) -> int | None:
        with suppress(TypeError):
            return self.time_control_initial_time // 60

    @property
    def time_control_initial_time_seconds(self) -> int | None:
        with suppress(TypeError):
            return self.time_control_initial_time % 60

    @property
    def handicap_str(self) -> str | None:
        if self.time_control_initial_time is None:
            return None
        (minutes, seconds) = divmod(self.time_control_initial_time, 60)
        minutes_str: str = f"{minutes}'" if minutes > 0 else ''
        seconds_str: str = f'{seconds}"' if seconds > 0 else ''
        class_str: str = 'modified-time' if self.time_control_modified else 'base-time'
        return f'<span class="{class_str}">{minutes_str}{seconds_str}</span> + {self.time_control_increment}"/cp'

    def set_time_control(self, initial_time: int, increment: int, modified: bool):
        self.time_control_initial_time = initial_time
        self.time_control_increment = increment
        self.time_control_modified = modified

    @property
    def tie_break_values_as_strings(self) -> list[str]:
        """Returns the player's tie-break values as strings."""
        assert self._tie_break_values is not None, \
            'Player._tie_break_values is not set, call Tournament.compute_player_ranks_after_round() before.'
        return [
            self._points_str(float(tie_break_value))
            for tie_break_value in self._tie_break_values
            if isinstance(tie_break_value, SupportsFloat)
        ]

    def compute_tie_break_values_after_round(
        self,
        round_: int | None = None
    ):
        self._tie_break_values = [
            tie_break.compute_player_value_after_round(self, round_)
            for tie_break in self.tournament.tie_breaks
        ]

    @property
    def rank(self) -> int:
        assert self._rank, 'Player._rank is not set, call Tournament.compute_player_ranks_after_round() before.'
        return self._rank

    def set_rank(self, rank: int):
        self._rank = rank

    @cached_property
    def crosstable_strings(self) -> list[str]:
        return [
            pairing.result.to_crosstable + (
                f'{self.tournament.players_by_id[pairing.opponent_id].rank:>3}'
                f'{pairing.color.to_crosstable}'
                if pairing.opponent_id else
                ''
            )
            for pairing in self.pairings.values()
        ]

    @property
    def starting_rank_sort_key(self) -> tuple[int, int, str, str]:
        return -self.rating, -self.title, self.last_name, self.first_name

    @property
    def board_number_sort_key(self) -> tuple[float, int, int, str, str]:
        return -self.vpoints, -self.rating, -self.title, self.last_name, self.first_name

    @property
    def rank_sort_key(self) -> tuple:
        tie_breaks = tuple(
            (-tie_break for tie_break in self._tie_break_values)
        )
        return (-self.points,) + tie_breaks + self.starting_rank_sort_key

    def __le__(self, other: 'Player') -> bool:
        # p1 <= p2 calls p1.__le__(p2)
        if not isinstance(other, Player):
            return NotImplemented
        # A false positive warning is raised in PyCharm, cf https://youtrack.jetbrains.com/issue/PY-76256
        return self.board_number_sort_key > other.board_number_sort_key

    def __eq__(self, other):
        # p1 == p2 calls p1.__eq__(p2)
        if not isinstance(other, Player):
            return NotImplemented
        return self.board_number_sort_key == other.board_number_sort_key

    def __repr__(self):
        if self.ref_id == 1:
            return f'{self.__class__.__name__}(#{self.id} PAB)'
        return (
            f'{self.__class__.__name__}'
            f'(#{self.id} title={self.title.value} gender={self.gender.value} '
            f'date_of_birth={self.date_of_birth} {self.last_name} {self.first_name} {self.club})'
        )
