import base64
import weakref
from collections import Counter
from dataclasses import dataclass, field
from functools import total_ordering, cached_property
from typing import Optional, Self, SupportsFloat, TYPE_CHECKING

from utils import StaticUtils
from utils.enum import (
    PlayerTitle,
    TitleNorm,
    PlayerRatingType,
)

if TYPE_CHECKING:
    from _weakref import ReferenceType
    from data.tie_breaks.tie_breaks import TieBreak
    from data.player import Player


@dataclass(frozen=True)
@total_ordering
class Federation:
    name: str = ''

    @cached_property
    def to_query_param(self) -> str:
        return base64.b64encode(self.name.encode('utf-8')).decode('utf-8')

    @classmethod
    def from_query_param(cls, query_param: str) -> Self:
        return cls(base64.b64decode(query_param).decode('utf-8'))

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
        return cls(base64.b64decode(query_param).decode('utf-8'))

    def __le__(self, other: Self):
        # p1 <= p2 calls p1.__le__(p2)
        assert isinstance(other, self.__class__), (
            f'Can not compare [{type(other)}] and [{self.__class__}]'
        )
        return self.name <= other.name

    def __str__(self) -> str:
        return self.name


@dataclass
class PlayerRating:
    estimated: int | None = None
    national: int | None = None
    fide: int | None = None

    @classmethod
    def from_stored_value(cls, dict_rating: dict[str, int | None]) -> Self:
        return cls(
            estimated=dict_rating.get('estimated'),
            national=dict_rating.get('national'),
            fide=dict_rating.get('fide'),
        )

    @classmethod
    def from_type(cls, value: int | None, rating_type: PlayerRatingType) -> Self:
        match rating_type:
            case PlayerRatingType.FIDE:
                return cls(fide=value)
            case PlayerRatingType.NATIONAL:
                return cls(national=value)
            case PlayerRatingType.ESTIMATED:
                return cls(estimated=value)
            case _:
                raise ValueError(f'{rating_type=}')

    @property
    def stored_value(self) -> dict[str, int | None]:
        return {
            'estimated': self.estimated,
            'national': self.national,
            'fide': self.fide,
        }

    def __str__(self) -> str:
        parts = []
        if self.fide is not None:
            parts.append(f'{self.fide}{PlayerRatingType.FIDE.short_name}')
        if self.national is not None:
            parts.append(f'{self.national}{PlayerRatingType.NATIONAL.short_name}')
        if self.estimated is not None:
            parts.append(f'{self.estimated}{PlayerRatingType.ESTIMATED.short_name}')
        return '/'.join(parts) if parts else '-'


@dataclass
class PlayerRatingAndType:
    value: int
    type: PlayerRatingType

    def __str__(self) -> str:
        return f'{self.value} {self.type.short_name}'


@dataclass
class NormCheckResult:
    title_norm: TitleNorm
    meets_gender: bool

    played_games: int = 0
    federations_count: int = 0
    from_own_federations_count: int = 0
    from_host_federations_count: int = 0
    num_title_holders: int = 0
    title_counts: Optional[Counter[PlayerTitle]] = None
    required_titles: list[PlayerTitle] = field(default_factory=list)
    required_titles_met: int = 0
    num_rated_players: int = 0
    score: float = 0
    average_rating: float = 0
    adjusted_player: Optional['Player'] = None
    adjusted_player_rating: Optional[int] = None
    performance: float = 0
    performance_diff: float | None = None
    ignored_opponents_ids: set[int] = field(default_factory=set)

    all_federations_count: int = 0
    eligible_players_count: int = 0
    eligible_players_title_count: int = 0

    not_enough_games: str | None = None
    not_enough_federations: str | None = None
    too_many_own_federation: str | None = None
    too_many_one_federation: Optional[tuple[Federation, str]] = None
    not_enough_title_holders: str | None = None
    not_enough_required_titles: str | None = None
    score_too_low: str | None = None
    average_too_low: str | None = None
    performance_too_low: str | None = None

    # 1.4.3d
    not_enough_all_federations: str | None = None
    not_enough_foreign_players: str | None = None
    not_enough_all_title_holders: str | None = None

    # 1.5.6a
    requirement_156a_met: bool = False

    @property
    def is_143d_met(self) -> bool:
        return (
            not self.not_enough_all_federations
            and not self.not_enough_foreign_players
            and not self.not_enough_all_title_holders
        )

    @property
    def is_met(self) -> bool:
        return self.meets_gender and not (
            self.not_enough_games
            or self.not_enough_federations
            or self.too_many_own_federation
            or self.too_many_one_federation
            or self.not_enough_title_holders
            or self.not_enough_required_titles
            or self.score_too_low
            or self.average_too_low
            or self.performance_too_low
        )


class TieBreakValue:
    def __init__(self, tie_break: 'TieBreak', value: SupportsFloat):
        self._tie_break_ref: 'ReferenceType[TieBreak]' = weakref.ref(tie_break)
        self.value = value
        self.rank_progress: int | None = None

    @property
    def tie_break(self) -> 'TieBreak':
        if (tie_break := self._tie_break_ref()) is None:
            raise RuntimeError('Reference has been garbage collected')
        return tie_break

    def __str__(self) -> str:
        if self.rank_progress is not None:
            if self.rank_progress > 0:
                return f'▲ {self.rank_progress}'
            if self.rank_progress < 0:
                return f'▼ {-self.rank_progress}'
            return ''
        return StaticUtils.points_str(float(self.value))
