import weakref
from _weakref import ReferenceType
from collections.abc import Collection
from typing import TYPE_CHECKING

from data.player import Player
from data.prize.managers import PrizeSharingManager
from data.prize.prize_criterion import PrizeCriterion
from data.prize.prize import Prize
from data.prize.prize_sharing import PrizeSharing, NoPrizeSharing
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPrizeCategory, StoredPrize

if TYPE_CHECKING:
    from data.prize.prize_group import PrizeGroup


class PrizeCategory:
    def __init__(
        self, prize_group: 'PrizeGroup', stored_prize_category: StoredPrizeCategory
    ):
        self._prize_group_ref: 'ReferenceType[PrizeGroup]' = weakref.ref(prize_group)
        self.stored_prize_category = stored_prize_category
        self.criteria_by_id = self._get_criteria_by_id()
        self.prizes_by_id = self._get_prizes_by_id()

    def _get_criteria_by_id(self) -> dict[int, PrizeCriterion]:
        criteria_by_id = {}
        for stored_criterion in self.stored_prize_category.stored_prize_criteria:
            assert stored_criterion.id is not None
            criteria_by_id[stored_criterion.id] = PrizeCriterion(self, stored_criterion)
        return criteria_by_id

    def _get_prizes_by_id(self) -> dict[int, Prize]:
        prizes_by_id = {}
        for stored_entry in self.stored_prize_category.stored_prizes:
            assert stored_entry.id is not None
            prizes_by_id[stored_entry.id] = Prize(self, stored_entry)
        return prizes_by_id

    @property
    def prize_group(self) -> 'PrizeGroup':
        if (prize_group := self._prize_group_ref()) is None:
            raise RuntimeError('Reference has been garbage collected')
        return prize_group

    @property
    def id(self) -> int:
        assert self.stored_prize_category.id is not None
        return self.stored_prize_category.id

    @property
    def name(self) -> str:
        return self.stored_prize_category.name

    @property
    def is_main(self) -> bool:
        return self.stored_prize_category.is_main

    @property
    def prize_sharing(self) -> PrizeSharing:
        return PrizeSharingManager.get_object(self.stored_prize_category.prize_sharing)

    @property
    def criteria(self) -> Collection[PrizeCriterion]:
        return self.criteria_by_id.values()

    @property
    def prizes(self) -> Collection[Prize]:
        return self.prizes_by_id.values()

    @property
    def sorted_prizes(self) -> list[Prize]:
        return sorted(self.prizes, key=lambda prize: prize.index)

    @property
    def players(self) -> list[Player]:
        return [
            player
            for player in self.prize_group.tournament.players
            if all(
                criterion.player_filter.is_player_included(player)
                for criterion in self.criteria
            )
        ]

    @property
    def criteria_string(self) -> str:
        return ', '.join(str(criterion.player_filter) for criterion in self.criteria)

    @property
    def are_prizes_shared(self) -> bool:
        return self.prize_sharing != NoPrizeSharing()

    @property
    def has_non_monetary_prizes(self):
        return any(not prize.is_monetary for prize in self.prizes)

    @property
    def total_prize_value(self) -> int:
        return sum(prize.value for prize in self.prizes)

    def get_event_database(self) -> EventDatabase:
        return self.prize_group.get_event_database()

    def update(self):
        with self.get_event_database() as database:
            database.update_stored_prize_category(self.stored_prize_category)
            database.commit()

    def get_default_prize_index(self, value: int):
        return next(
            (
                index
                for index, prize in enumerate(self.sorted_prizes)
                if prize.value < value
            ),
            len(self.prizes),
        )

    def add_prize(self, stored_prize: StoredPrize) -> Prize:
        with self.get_event_database() as database:
            object_id = database.add_stored_prize(stored_prize)
            database.commit()
        prize = Prize(self, stored_prize)
        stored_prize.id = object_id
        prize_ids = [prize.id for prize in self.sorted_prizes]
        prize_ids.insert(stored_prize.index, object_id)
        self.prizes_by_id[object_id] = prize
        self.reorder_prizes(prize_ids)
        return prize

    def delete_prize(self, prize_id: int):
        with self.get_event_database() as database:
            database.delete_stored_prize(prize_id)
            database.commit()
        if prize_id in self.prizes_by_id:
            del self.prizes_by_id[prize_id]
        self.reorder_prizes([prize.id for prize in self.sorted_prizes])

    def reorder_prizes(self, sorted_prize_ids: list[int]):
        with self.get_event_database() as database:
            for prize in self.prizes:
                if prize.id not in sorted_prize_ids:
                    raise ValueError(f'Missing prize id: {prize.id}')
                index = sorted_prize_ids.index(prize.id)
                if index != prize.index:
                    prize.stored_prize.index = index
                    database.update_stored_prize_index(prize.id, index)
            database.commit()
