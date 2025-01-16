import base64
from contextlib import suppress
from dataclasses import dataclass
from datetime import date
from functools import total_ordering, cached_property
from logging import Logger
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from data.tournament import Tournament

from common.i18n import _
from data.pairing import Pairing
from common.logger import get_logger
from data.util import PlayerGender, PlayerTitle, Color, PlayerFFELicence, TournamentRating, PlayerRatingType

logger: Logger = get_logger()

@dataclass(frozen=True)
@total_ordering
class FederationTuple:
    federation: str = ''

    @classmethod
    def string_tuple_to_query_param(cls, strings: tuple[str, ...]) -> str:
        return '-' + '-'.join([
            base64.b64encode(string.encode('utf-8')).decode('utf-8')
            for string in strings
        ])

    @classmethod
    def query_param_to_string_tuple(cls, query_param: str) -> tuple[str, ...]:
        return tuple(
            base64.b64decode(string).decode('utf-8')
            for string in query_param[1:].split('-')
        )

    @cached_property
    def to_query_param(self) -> str:
        return self.string_tuple_to_query_param((self.federation, ))

    @classmethod
    def from_query_param(cls, query_param: str) -> Self:
        t: tuple[str, ...] = cls.query_param_to_string_tuple(query_param)
        return FederationTuple(t[0])

    def __le__(self, other: Self):
        # p1 <= p2 calls p1.__le__(p2)
        assert isinstance(other, self.__class__), f'Can not compare [{type(other)}] and [{self.__class__}]'
        return self.federation <= other.federation

    def __eq__(self, other: Self):
        # p1 == p2 calls p1.__eq__(p2)
        assert isinstance(other, self.__class__), f'Can not compare [{type(other)}] and [{self.__class__}]'
        return self.federation == other.federation

    def __str__(self) -> str:
        return self.federation


@dataclass(frozen=True)
@total_ordering
class LeagueTuple(FederationTuple):
    league: str = ''

    @cached_property
    def to_query_param(self) -> str:
        return self.string_tuple_to_query_param((self.federation, self.league))

    @classmethod
    def from_query_param(cls, query_param: str) -> Self:
        t: tuple[str, ...] = cls.query_param_to_string_tuple(query_param)
        return LeagueTuple(t[0], t[1])

    def __le__(self, other: Self):
        # p1 <= p2 calls p1.__le__(p2)
        assert isinstance(other, self.__class__), f'Can not compare [{type(other)}] and [{self.__class__}]'
        return (self.federation, self.league) <= (other.federation, other.league)

    def __eq__(self, other: Self):
        # p1 == p2 calls p1.__eq__(p2)
        assert isinstance(other, self.__class__), f'Can not compare [{type(other)}] and [{self.__class__}]'
        return self.federation == other.federation and self.league == other.league

    def __str__(self) -> str:
        return f'{self.federation}-{self.league}'


@dataclass(frozen=True)
@total_ordering
class ClubTuple(LeagueTuple):
    club: str = ''

    @cached_property
    def to_query_param(self) -> str:
        return self.string_tuple_to_query_param((self.federation, self.league, self.club))

    @classmethod
    def from_query_param(cls, query_param: str) -> Self:
        t: tuple[str, ...] = cls.query_param_to_string_tuple(query_param)
        return ClubTuple(t[0], t[1], t[2])

    def __le__(self, other: Self):
        # p1 <= p2 calls p1.__le__(p2)
        assert isinstance(other, self.__class__), f'Can not compare [{type(other)}] and [{self.__class__}]'
        return (self.federation, self.league, self.club) <= (other.federation, other.league, other.club)

    def __eq__(self, other: Self):
        # p1 == p2 calls p1.__eq__(p2)
        assert isinstance(other, self.__class__), f'Can not compare [{type(other)}] and [{self.__class__}]'
        return self.federation == other.federation and self.league == other.league and self.club == other.club

    def __str__(self) -> str:
        return f'{self.federation}-{self.league}-{self.club}'


@total_ordering
class Player:
    """A data class representing a player in a tournament."""
    def __init__(
            self,
            id: int,
            last_name: str,
            first_name: str,
            date_of_birth: date | None,
            gender: PlayerGender,
            mail: str,
            phone: str,
            comment: str,
            owed: float,
            paid: float,
            title: PlayerTitle,
            ratings: dict[TournamentRating, int],
            rating_types: dict[TournamentRating, PlayerRatingType],
            fide_id: int | None,
            ffe_id: int,
            ffe_licence: PlayerFFELicence,
            ffe_licence_number: str | None,
            federation: str,
            league: str,
            club: str,
            fixed: int,
            check_in: bool,
            pairings: dict[int, Pairing],
            tournament: 'Tournament | None' = None,
            errors: dict[str, str] | None = None,
    ):
        self.id: int = id
        self.last_name: str = last_name
        self.first_name: str = first_name
        self.date_of_birth: date | None = date_of_birth
        self.gender: PlayerGender = gender
        self.mail: str = mail
        self.phone: str = phone
        self.comment: str = comment
        self.owed: float = owed
        self.paid: float = paid
        self.title: PlayerTitle = title
        self.ratings: dict[TournamentRating, int] = ratings
        self.rating_types: dict[TournamentRating, PlayerRatingType] = rating_types
        self.fide_id: int | None = fide_id
        self.ffe_id: int = ffe_id
        self.ffe_licence: PlayerFFELicence = ffe_licence
        self.ffe_licence_number: str | None = ffe_licence_number
        self.federation: str = federation
        self.league: str = league
        self.club: str = club
        self.fixed: int = fixed
        self.check_in: bool = check_in
        self.pairings: dict[int, Pairing] = pairings
        self.points: float | None = None
        self.vpoints: float | None = None
        self.board_id: int | None = None
        self.board_number: int | None = None
        self.color: Color | None = None
        self.illegal_moves: int = 0
        self.time_control_initial_time: int | None = None
        self.time_control_increment: int | None = None
        self.time_control_modified: bool | None = None
        self.tournament: Tournament | None = tournament
        self.errors: dict[str, str] = errors or {}

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
        """ Returns the Unique ID of the player in the Papi file (needed while using the Papi storage)."""
        return self.player_papi_id_from_papi_web_id(self.id)

    @property
    def tournament_id(self) -> int:
        return self.player_tournament_id_from_papi_web_id(self.id)

    @property
    def year_of_birth(self) -> int:
        return self.date_of_birth.year if self.date_of_birth else 0

    @property
    def rating(self) -> int:
        return self.ratings[self.tournament.rating]

    @property
    def rating_type(self) -> PlayerRatingType:
        return self.rating_types[self.tournament.rating]

    @cached_property
    def club_tuple(self) -> ClubTuple:
        return ClubTuple(self.federation, self.league, self.club)

    @cached_property
    def league_tuple(self) -> LeagueTuple:
        return LeagueTuple(self.federation, self.league)

    @cached_property
    def federation_tuple(self) -> FederationTuple:
        return FederationTuple(self.federation)

    def compute_points(self, max_round: int):
        """Computes and stores the points of the player,
        from round 1 to round `max_round` (returns None)"""
        # NOTE(Amaras) this does not rely on the fact that insertion order
        # is preserved in 3.6+ dict, because I can't be sure insertion order
        # is the correct (increasing) round order
        self.points = sum(
                pairing.result.point_value
                for round_index, pairing in self.pairings.items()
                # NOTE(Amaras) if you were to include the current round
                # in the computation, boards regularly change their ordering
                # during the current round as results are added
                if round_index < max_round)

    @staticmethod
    def _points_str(points: float | None) -> str:
        if points is None:
            return ''
        if points == 0.5:
            return '½'
        return '{:.1f}'.format(points).replace('.0', '').replace('.5', '½')

    def add_points(self, points: float):
        """If `self.points` is set, add `points` to it.
        Otherwise, leave `self.points` as None."""
        with suppress(TypeError):
            self.points += points

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
        return _('Unpaired *** FEMALE') if self.gender == PlayerGender.FEMALE else _('Unpaired *** MALE')

    @property
    def exempt_str(self) -> str:
        return _('Exempt *** FEMALE') if self.gender == PlayerGender.FEMALE else _('Exempt *** MALE')

    def set_board(self, board_id: int, board_number: int, color: Color):
        self.board_id = board_id
        self.board_number = board_number
        self.color = color

    @cached_property
    def has_real_pairings(self) -> bool:
        """ Returns True if the player has already been paired with an opponent
        (i.e. can not be deleted from the tournament anymore)."""
        for pairing in self.pairings.values():
            if pairing.opponent_papi_id and pairing.opponent_papi_id > 1:
                return True
        return False

    @cached_property
    def can_check_in_out(self) -> bool:
        """ Returns True if the player can check-in/out, i.e. it is not forfeit for the next round. """
        if self.tournament.finished:
            return False
        if self.tournament.playing:
            return False
        if not self.tournament.check_in_open:
            return False
        pairing: Pairing = self.pairings[self.tournament.current_round + 1]
        return not pairing.forfeit and not pairing.half_point_bye and not pairing.full_point_bye

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
        minutes_str: str = f'{minutes}\'' if minutes > 0 else ''
        seconds_str: str = f'{seconds}"' if seconds > 0 else ''
        class_str: str = 'modified-time' if self.time_control_modified else 'base-time'
        return f'<span class="{class_str}">{minutes_str}{seconds_str}</span> + {self.time_control_increment}"/cp'

    def set_time_control(self, initial_time: int, increment: int, modified: bool):
        self.time_control_initial_time = initial_time
        self.time_control_increment = increment
        self.time_control_modified = modified

    def __le__(self, other):
        # p1 <= p2 calls p1.__le__(p2)
        if not isinstance(other, Player):
            return NotImplemented
        return (self.vpoints, self.rating, self.title, other.last_name,
                other.first_name) <= (other.vpoints, other.rating, other.title,
                                      self.last_name, self.first_name)

    def __eq__(self, other):
        # p1 == p2 calls p1.__eq__(p2)
        if not isinstance(other, Player):
            return NotImplemented
        return (
            self.vpoints == other.vpoints and self.rating == other.rating and
            self.title == other.title and self.last_name == other.last_name and
            self.first_name == other.first_name
        )

    def __repr__(self):
        if self.ref_id == 1:
            return f'{self.__class__.__name__}(#{self.id} PAB)'
        return (f'{self.__class__.__name__}'
                f'(#{self.id} {self.title.short_name}{self.last_name} {self.first_name} {self.rating} [{self.vpoints}])')
