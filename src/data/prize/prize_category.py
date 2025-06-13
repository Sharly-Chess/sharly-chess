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
from database.sqlite.event.event_store import (
    StoredPrizeCategory,
    StoredPrize,
    StoredPrizeCriterion,
)
from utils import StaticUtils

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
    def threshold(self) -> float | None:
        return self.stored_prize_category.threshold

    @property
    def index(self) -> int:
        return self.stored_prize_category.index

    @property
    def prize_sharing(self) -> PrizeSharing:
        return PrizeSharingManager.get_object(self.stored_prize_category.prize_sharing)

    @property
    def criteria(self) -> Collection[PrizeCriterion]:
        return self.criteria_by_id.values()

    @property
    def sorted_criteria(self) -> list[PrizeCriterion]:
        return sorted(self.criteria, key=lambda criteria: criteria.id)

    @property
    def prizes(self) -> Collection[Prize]:
        return self.prizes_by_id.values()

    @property
    def sorted_prizes(self) -> list[Prize]:
        return sorted(
            self.prizes,
            key=lambda prize: (-prize.value, not prize.is_monetary, prize.id),
        )

    def player_matches_criteria(self, player: Player) -> bool:
        """Check if the player matches all criteria of this category."""
        return all(
            criterion.player_filter.is_player_included_function(player)
            for criterion in self.criteria
        )

    @property
    def players(self) -> list[Player]:
        return [
            player
            for player in self.prize_group.tournament.players
            if self.player_matches_criteria(player)
        ]

    @property
    def criteria_string(self) -> str:
        return ', '.join(criterion.name for criterion in self.criteria)

    @property
    def are_prizes_shared(self) -> bool:
        return self.prize_sharing != NoPrizeSharing()

    @property
    def has_non_monetary_prizes(self):
        return any(not prize.is_monetary for prize in self.prizes)

    @property
    def total_prize_value(self) -> float:
        return sum(prize.value for prize in self.prizes)

    @property
    def total_prize_value_str(self) -> str:
        return StaticUtils.currency_value_str(self.total_prize_value, self.currency)

    @property
    def currency(self) -> str:
        return self.prize_group.tournament.event.prize_currency

    def get_event_database(self) -> EventDatabase:
        return self.prize_group.get_event_database()

    def update(self):
        with self.get_event_database() as database:
            database.update_stored_prize_category(self.stored_prize_category)
            database.commit()

    def add_criterion(self, stored_criterion: StoredPrizeCriterion) -> PrizeCriterion:
        with self.get_event_database() as database:
            object_id = database.add_stored_prize_criterion(stored_criterion)
            database.commit()
        stored_criterion.id = object_id
        prize_criterion = PrizeCriterion(self, stored_criterion)
        self.criteria_by_id[object_id] = prize_criterion
        return prize_criterion

    def delete_criterion(self, criterion_id: int):
        with self.get_event_database() as database:
            database.delete_stored_prize_criterion(criterion_id)
            database.commit()
        if criterion_id in self.criteria_by_id:
            del self.criteria_by_id[criterion_id]

    def add_prize(self, stored_prize: StoredPrize) -> Prize:
        with self.get_event_database() as database:
            object_id = database.add_stored_prize(stored_prize)
            database.commit()
        prize = Prize(self, stored_prize)
        stored_prize.id = object_id
        self.prizes_by_id[object_id] = prize
        return prize

    def delete_prize(self, prize_id: int):
        with self.get_event_database() as database:
            database.delete_stored_prize(prize_id)
            database.commit()
        if prize_id in self.prizes_by_id:
            del self.prizes_by_id[prize_id]

    def __repr__(self):
        return f'{self.__class__.__name__} - {self.id}/{self.name}'
