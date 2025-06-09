from types import NotImplementedType
import weakref
from _weakref import ReferenceType
from typing import TYPE_CHECKING

from common.i18n import _
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPrize
from utils import StaticUtils

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
    def value(self) -> float:
        return self.stored_prize.value

    @property
    def is_monetary(self) -> bool:
        return self.stored_prize.is_monetary

    @property
    def description(self) -> str:
        return self.stored_prize.description

    @property
    def name(self) -> str:
        if self.is_monetary:
            return self.format_value()
        description = self.description or _('Non-monetary prize')
        if not self.value:
            return description
        value_str = _('value: {currency_value}').format(
            currency_value=self.format_value()
        )
        return f'{description} ({value_str})'

    def format_value(self, value: float | None = None) -> str:
        if value is None:
            value = self.value
        return StaticUtils.currency_value_str(value, self.prize_category.currency)

    def get_event_database(self) -> EventDatabase:
        return self.prize_category.get_event_database()

    def update(self):
        with self.get_event_database() as database:
            database.update_stored_prize(self.stored_prize)
            database.commit()

    def __eq__(self, other: object) -> bool | NotImplementedType:
        # p1 == p2 calls p1.__eq__(p2)
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.id == other.id

    def __repr__(self):
        return f'{self.__class__.__name__} - {self.stored_prize}'
