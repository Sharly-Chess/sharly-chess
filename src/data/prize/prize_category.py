import weakref
from _weakref import ReferenceType
from collections.abc import Collection
from typing import TYPE_CHECKING

from data.player import Player
from data.prize.managers import PrizeSharingManager
from data.prize.prize_criterion import PrizeCriterion
from data.prize.prize import Prize
from data.prize.prize_sharing import PrizeSharing
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPrizeCategory

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
    def total_prize_value(self) -> int:
        return sum(prize.value for prize in self.prizes)

    def get_event_database(self) -> EventDatabase:
        return self.prize_group.get_event_database()

    def update(self):
        with self.get_event_database() as database:
            database.update_stored_prize_category(self.stored_prize_category)
            database.commit()
