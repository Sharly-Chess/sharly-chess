import weakref
from _weakref import ReferenceType
from typing import TYPE_CHECKING

from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPrize

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

    @property
    def value(self) -> int:
        return self.stored_prize.value

    @property
    def is_monetary(self) -> bool:
        return self.stored_prize.is_monetary

    @property
    def description(self) -> str | None:
        return self.stored_prize.description

    @property
    def index(self) -> int:
        return self.stored_prize.index

    def get_event_database(self) -> EventDatabase:
        return self.prize_category.get_event_database()
