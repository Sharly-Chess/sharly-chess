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
        for stored_category in self.stored_prize_group.stored_prized_categories:
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
        return sorted(
            self.categories,
            key=lambda category: (
                -category.is_main,
                -category.total_prize_value,
                category.name,
            ),
        )

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
        with self.get_event_database() as database:
            object_id = database.add_stored_prize_category(stored_category)
            database.commit()
        stored_category.id = object_id
        category = PrizeCategory(self, stored_category)
        self.categories_by_id[object_id] = category
        return category

    def delete_category(self, category_id: int):
        with self.get_event_database() as database:
            database.delete_stored_prize_category(category_id)
            database.commit()

        if category_id in self.categories_by_id:
            del self.categories_by_id[category_id]
