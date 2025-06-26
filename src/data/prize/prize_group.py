from collections import deque
import weakref
from _weakref import ReferenceType
from collections.abc import Collection
from typing import TYPE_CHECKING

from common.i18n import _
from data.player import Player
from data.prize.assigned_prize import AssignedPrize
from data.prize.prize import Prize
from data.prize.prize_category import PrizeCategory
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPrizeGroup, StoredPrizeCategory
from utils import StaticUtils

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

    # ---------------------------------------------------------------------------------
    # Calculation
    # ---------------------------------------------------------------------------------

    def assign_prizes(self):
        self.tournament.compute_player_ranks(
            correct_round=False, after_round=self.tournament.max_ranking_round
        )
        sorted_players: list[Player] = list(self.tournament.players_by_rank.values())
        assigned_prizes: dict[int, AssignedPrize] = {}
        unassigned_prizes: list[AssignedPrize] = []
        removed_from_main_set: set[int] = set()
        queue: deque[AssignedPrize] = deque()

        # Extract general prizes
        main_category = next(
            (category for category in self.categories if category.is_main), None
        )
        main_prizes = list(main_category.sorted_prizes) if main_category else []

        def calculate_main_category_prizes(
            sorted_players: list[Player],
        ) -> list[AssignedPrize]:
            """Returns all the players eligible to receive a prize from the main category"""

            if main_category is None:
                return []

            filtered_players = [
                player
                for player in sorted_players
                if player.id not in removed_from_main_set
            ]

            return main_category.prize_sharing.calculate_prizes(
                main_prizes, filtered_players, threshold=main_category.sharing_threshold
            )

        top_prizes = calculate_main_category_prizes(sorted_players)
        top_players = [
            assigned_prize.assigned_to
            for assigned_prize in top_prizes
            if assigned_prize.assigned_to
        ]

        # Assign initial main category prizes
        for assigned_prize in top_prizes:
            if assigned_prize.assigned_to:
                assigned_prizes[assigned_prize.assigned_to.id] = assigned_prize

        # Flatten all non-main prize slots into a queue
        for category in self.sorted_categories:
            for place, prize in enumerate(category.sorted_prizes):
                if prize not in main_prizes:
                    queue.append(
                        AssignedPrize(
                            prize=prize,
                            priority=category.index,
                            place_index=place,
                            assigned_to=None,
                            value=prize.value,
                        )
                    )

        # Sort queue
        queue = deque(
            sorted(
                queue,
                key=lambda p: (
                    -p.prize.value if p.prize else 0,
                    p.priority,
                    p.place_index,
                ),
            )
        )

        # Find eligible player for a prize
        def find_eligible_player(prize: Prize):
            for player in sorted_players:
                if not prize.prize_category.player_matches_criteria(player):
                    continue
                current = assigned_prizes.get(player.id)
                if not current or current.value < prize.value:
                    return player
            return None

        # Main prize assignment loop
        while queue:
            prize_slot = queue.popleft()
            next_prize = prize_slot.prize
            assert next_prize is not None, 'Prize slot must have a prize'

            player = find_eligible_player(next_prize)
            if not player:
                unassigned_prizes.append(prize_slot)
                continue

            current = assigned_prizes.get(player.id)
            is_upgrade = not current or next_prize.value > current.value or 0
            if not is_upgrade:
                continue

            warning: str | None = None

            if current:
                # The player has currently won a less valuable prize
                if current.is_main:
                    # The player has currently won a less valuable main prize
                    # Remove the player from the main group
                    removed_from_main_set.add(player.id)
                    iterate = True

                    new_top_players: list[Player] = []
                    new_top_prizes: list[AssignedPrize] = []

                    while iterate:
                        new_top_prizes = calculate_main_category_prizes(sorted_players)
                        new_top_players = [
                            assigned_prize.assigned_to
                            for assigned_prize in top_prizes
                            if assigned_prize.assigned_to
                        ]

                        new_top_player_ids = [player.id for player in new_top_players]
                        iterate = False

                        newly_entered_players_ids = list(
                            set(new_top_player_ids)
                            - set(player.id for player in top_players)
                        )

                        for player_id in newly_entered_players_ids:
                            new_main_shared_prize = next(
                                (
                                    assigned_prize
                                    for assigned_prize in new_top_prizes
                                    if assigned_prize.assigned_to
                                    and assigned_prize.assigned_to.id == player_id
                                ),
                                None,
                            )
                            players_current_prize = assigned_prizes.get(player_id, None)
                            players_current_prize_value = (
                                players_current_prize.value
                                if players_current_prize
                                else 0
                            )
                            if players_current_prize:
                                if (
                                    new_main_shared_prize
                                    and new_main_shared_prize.value
                                    > players_current_prize_value
                                    and players_current_prize.prize
                                ):
                                    # If the newly entered player now has a higher prize value than the current one,
                                    # we add the old on back to the queue
                                    queue.append(
                                        AssignedPrize(
                                            prize=players_current_prize.prize,
                                            priority=players_current_prize.priority,
                                            place_index=players_current_prize.place_index,
                                            assigned_to=None,
                                            value=players_current_prize_value,
                                        )
                                    )
                                else:
                                    # Otherwise if the current prize is higher than the new one, we remove the player
                                    # from the main group and continue to add new players to the group if needed
                                    removed_from_main_set.add(player.id)
                                    iterate = True

                    top_players = new_top_players
                    for assigned_prize in new_top_prizes:
                        if assigned_prize.assigned_to:
                            assigned_prizes[assigned_prize.assigned_to.id] = (
                                assigned_prize
                            )

                    # Find out how much the same place is worth now that the player has left the main category
                    prize_with_same_place = next(
                        (
                            assigned_prize
                            for assigned_prize in assigned_prizes.values()
                            if assigned_prize.is_main
                            and assigned_prize.place_index == current.place_index
                            and assigned_prize.assigned_to
                            and assigned_prize.assigned_to.id != player.id
                        ),
                        None,
                    )

                    if (
                        prize_with_same_place
                        and next_prize.value < prize_with_same_place.value
                    ):
                        warning = _(
                            "{player.first_name} {player.last_name} had won {previous_value} in the main group but was then given a prize of {next_value} in the category '{cat_name}' instead. By leaving the main group, the prize share for the place they were in is now worth {new_share}."
                        ).format(
                            player=player,
                            previous_value=StaticUtils.currency_value_str(
                                current.value, next_prize.prize_category.currency
                            ),
                            next_value=StaticUtils.currency_value_str(
                                next_prize.value, next_prize.prize_category.currency
                            ),
                            cat_name=next_prize.prize_category.name,
                            new_share=StaticUtils.currency_value_str(
                                prize_with_same_place.value,
                                next_prize.prize_category.currency,
                            ),
                        )
                else:
                    # The new prize is higher than the current one, we add the previous prize back to the queue
                    current.assigned_to = None
                    queue.append(current)

                # Resort the queue since it might have changed
                queue = deque(
                    sorted(
                        queue,
                        key=lambda p: (
                            -p.prize.value if p.prize else 0,
                            p.priority,
                            p.place_index,
                        ),
                    )
                )
                del assigned_prizes[player.id]

            # Assign the new prize
            assigned_prizes[player.id] = AssignedPrize(
                prize=prize_slot.prize,
                priority=prize_slot.priority,
                place_index=prize_slot.place_index,
                assigned_to=player,
                value=next_prize.value,
                warning=warning,
            )

        sorted_prizes = sorted(
            list(assigned_prizes.values()) + unassigned_prizes,
            key=lambda p: (-p.prize.value, p.priority, p.place_index),
        )

        return sorted_prizes

    def get_assigned_prizes_by_category_id(self) -> dict[int, list[AssignedPrize]]:
        assigned_prizes_by_category_id: dict[int, list[AssignedPrize]] = {
            category.id: [] for category in self.categories
        }
        for assigned_prize in self.assign_prizes():
            category_id = assigned_prize.prize.prize_category.id
            assigned_prizes_by_category_id[category_id].append(assigned_prize)
        for category_id in assigned_prizes_by_category_id:
            assigned_prizes_by_category_id[category_id] = sorted(
                assigned_prizes_by_category_id[category_id],
                key=lambda prize: (
                    prize.place_index,
                    prize.assigned_to is None,
                    prize.assigned_to.rank if prize.assigned_to else None,
                ),
            )
        return assigned_prizes_by_category_id
