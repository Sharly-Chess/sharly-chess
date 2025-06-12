import weakref
from _weakref import ReferenceType
from collections.abc import Collection
from typing import TYPE_CHECKING

from data.prize.prize_category import PrizeCategory
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPrizeGroup, StoredPrizeCategory

if TYPE_CHECKING:
    from data.tournament import Tournament


class PrizeGroup:
    def __init__(
        self,
        tournament: 'Tournament',
        stored_prize_group: StoredPrizeGroup,
    ):
        self._tournament_ref: 'ReferenceType[Tournament]' = weakref.ref(tournament)
        self.stored_prize_group = stored_prize_group
        self.categories_by_id = self._get_categories_by_id()

    def _get_categories_by_id(self) -> dict[int, PrizeCategory]:
        category_by_id = {}
        for stored_category in self.stored_prize_group.stored_prize_categories:
            assert stored_category.id is not None
            category_by_id[stored_category.id] = PrizeCategory(self, stored_category)
        return category_by_id

    @property
    def tournament(self) -> 'Tournament':
        if (tournament := self._tournament_ref()) is None:
            raise RuntimeError('Reference has been garbage collected')
        return tournament

    @property
    def id(self) -> int:
        assert self.stored_prize_group.id is not None
        return self.stored_prize_group.id

    @property
    def name(self) -> str:
        return self.stored_prize_group.name

    @property
    def categories(self) -> Collection[PrizeCategory]:
        return self.categories_by_id.values()

    @property
    def sorted_categories(self) -> list[PrizeCategory]:
        return sorted(self.categories, key=lambda category: category.index)

    @property
    def has_main_category(self) -> bool:
        return any(category.is_main for category in self.categories)

    def get_event_database(self) -> EventDatabase:
        return EventDatabase(self.tournament.event.uniq_id, True)

    def update(self):
        with self.get_event_database() as database:
            database.update_stored_prize_group(self.stored_prize_group)
            database.commit()

    def add_category(self, stored_category: StoredPrizeCategory) -> PrizeCategory:
        stored_category.index = (
            max((cat.index for cat in self.categories), default=0) + 1
        )
        with self.get_event_database() as database:
            object_id = database.add_stored_prize_category(stored_category)
            database.commit()
        stored_category.id = object_id
        category = PrizeCategory(self, stored_category)
        self.categories_by_id[object_id] = category
        if stored_category.is_main:
            category_ids = [category.id for category in self.sorted_categories]
            category_ids.remove(object_id)
            category_ids.insert(0, object_id)
            self.reorder_categories(category_ids)
        return category

    def delete_category(self, category_id: int):
        with self.get_event_database() as database:
            database.delete_stored_prize_category(category_id)
            database.commit()
        if category_id in self.categories_by_id:
            del self.categories_by_id[category_id]
        self.reorder_categories()

    def reorder_categories(self, sorted_category_ids: list[int] | None = None):
        if not sorted_category_ids:
            sorted_category_ids = [category.id for category in self.sorted_categories]
        with self.get_event_database() as database:
            for category in self.categories:
                if category.id not in sorted_category_ids:
                    raise ValueError(f'Missing category id: {category.id}')
                index = sorted_category_ids.index(category.id)
                if index != category.index:
                    category.stored_prize_category.index = index
                    database.update_stored_prize_category_index(category.id, index)
            database.commit()
