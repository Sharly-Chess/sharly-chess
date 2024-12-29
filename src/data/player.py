from functools import total_ordering
from logging import Logger
from dataclasses import dataclass, field
from contextlib import suppress

from common.i18n import _
from data.pairing import Pairing
from common.logger import get_logger
from data.util import PlayerGender, PlayerTitle, Color

logger: Logger = get_logger()


@dataclass
@total_ordering
class Player:
    """A data class representing a player in a tournament."""
    ref_id: int
    last_name: str
    first_name: str
    gender: PlayerGender
    title: PlayerTitle
    rating: int
    rating_type: str
    licence_type: str
    federation: str
    fixed: int
    check_in: bool
    pairings: dict[int, Pairing]
    points: float | None = field(default=None, init=False)
    vpoints: float | None = field(default=None, init=False)
    board_id: int | None = field(default=None, init=False)
    board_number: int | None = field(default=None, init=False)
    color: Color | None = field(default=None, init=False)
    illegal_moves: int = 0
    time_control_initial_time: int | None = field(default=None, init=False)
    time_control_increment: int | None = field(default=None, init=False)
    time_control_modified: bool | None = field(default=None, init=False)

    @property
    def id(self) -> int:
        return self.ref_id

    @property
    def title_str(self) -> str:
        return str(self.title)

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
        return _('Unpaired *** FEMALE ***') if self.gender == PlayerGender.FEMALE else _('Unpaired *** MALE ***')

    @property
    def exempt_str(self) -> str:
        return _('Exempt *** FEMALE ***') if self.gender == PlayerGender.FEMALE else _('Exempt *** MALE ***')

    def set_board(self, board_id: int, board_number: int, color: Color):
        self.board_id = board_id
        self.board_number = board_number
        self.color = color

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
        if self.id == 1:
            return f'{self.__class__.__name__}(EXEMPT)'
        return (f'{self.__class__.__name__}'
                f'({self.title_str}{self.last_name} {self.first_name} {self.rating} [{self.vpoints}])')
