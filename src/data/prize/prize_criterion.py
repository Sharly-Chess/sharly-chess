import weakref
from _weakref import ReferenceType
from typing import TYPE_CHECKING

from data.prize.managers import PlayerFilterManager
from data.prize.player_filters import PlayerFilter
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPrizeCriterion

if TYPE_CHECKING:
    from data.prize.prize_category import PrizeCategory


class PrizeCriterion:
    def __init__(
        self,
        prize_category: 'PrizeCategory',
        stored_prize_criterion: StoredPrizeCriterion,
    ):
        self._prize_category_ref: 'ReferenceType[PrizeCategory]' = weakref.ref(
            prize_category
        )
        self.stored_prize_criterion = stored_prize_criterion
        self.player_filter = self._get_player_filter()

    def _get_player_filter(self) -> PlayerFilter:
        filter_type = PlayerFilterManager.get_type(self.stored_prize_criterion.type)
        options = []
        for option in filter_type.default_options():
            value = self.stored_prize_criterion.options.get(
                option.id, option.default_value
            )
            options.append(type(option)(value))
        return filter_type(options)

    @property
    def prize_category(self) -> 'PrizeCategory':
        if (prize_category := self._prize_category_ref()) is None:
            raise RuntimeError('Reference has been garbage collected')
        return prize_category

    @property
    def id(self) -> int:
        assert self.stored_prize_criterion.id is not None
        return self.stored_prize_criterion.id

    @property
    def index(self) -> int:
        return self.stored_prize_criterion.index

    def get_event_database(self) -> EventDatabase:
        return self.prize_category.get_event_database()

    def update(self):
        with self.get_event_database() as database:
            database.update_stored_prize_criterion(self.stored_prize_criterion)
            database.commit()
        self.player_filter = self._get_player_filter()
