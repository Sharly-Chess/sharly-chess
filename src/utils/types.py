from dataclasses import dataclass
from functools import total_ordering, cached_property
import base64
from typing import Self

from utils.enum import PlayerRatingType


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


@total_ordering
@dataclass
class PlayerRating:
    """A representation of the player's rating.
    *value* is the numerical rating"""

    value: int
    type: PlayerRatingType

    @classmethod
    def from_stored_value(cls, dict_rating: dict[str, int]):
        return cls(dict_rating['value'], PlayerRatingType(dict_rating['type']))

    @property
    def fide_unrated(self) -> bool:
        return self.type != PlayerRatingType.FIDE

    def __lt__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        if self.fide_unrated and not other.fide_unrated:
            return False
        if not self.fide_unrated and other.fide_unrated:
            return True
        return self.value < other.value

    @property
    def stored_value(self) -> dict[str, int]:
        return {
            'value': self.value,
            'type': self.type.value,
        }

    def __str__(self) -> str:
        return f'{self.value} {self.type.short_name}'
