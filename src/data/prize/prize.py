from functools import cached_property
from types import NotImplementedType
import weakref
from _weakref import ReferenceType
from typing import TYPE_CHECKING

from data.prize.managers import PrizeTypeManager
from data.prize.prize_type import PrizeType
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPrize
from utils import Utils

if TYPE_CHECKING:
    from data.prize.prize_category import PrizeCategory


class Prize:
    def __init__(self, prize_category: 'PrizeCategory', stored_prize: StoredPrize):
        self._prize_category_ref: 'ReferenceType[PrizeCategory]' = weakref.ref(
            prize_category
        )
        self.stored_prize = stored_prize

    @property
    def prize_category(self) -> 'PrizeCategory':
        if (prize_category := self._prize_category_ref()) is None:
            raise RuntimeError('Reference has been garbage collected')
        return prize_category

    @property
    def id(self) -> int:
        assert self.stored_prize.id is not None
        return self.stored_prize.id

    @cached_property
    def type(self) -> PrizeType:
        return PrizeTypeManager().get_object(self.stored_prize.type)

    @property
    def value(self) -> float:
        return self.stored_prize.value

    @property
    def description(self) -> str:
        return self.stored_prize.description

    @property
    def is_monetary(self) -> bool:
        return self.type.is_monetary

    @property
    def name(self) -> str:
        return self.type.get_prize_name(self.value, self.description, self.currency)

    @property
    def full_name(self) -> str:
        return self.type.get_prize_full_name(
            self.value, self.description, self.currency
        )

    @cached_property
    def currency(self) -> str:
        return self.prize_category.prize_group.tournament.event.prize_currency

    def get_event_database(self) -> EventDatabase:
        return self.prize_category.get_event_database()

    def update(self):
        with self.get_event_database() as database:
            database.update_stored_prize(self.stored_prize)
        Utils.reset_cached_properties(self, 'type')

    def __eq__(self, other: object) -> bool | NotImplementedType:
        # p1 == p2 calls p1.__eq__(p2)
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.id == other.id

    def __str__(self):
        return f'{self.__class__.__name__} - {self.stored_prize}'

    def __repr__(self):
        return f'{self.__class__.__name__}(prize_category={self.prize_category!r}, stored_prize={self.stored_prize!r})'
