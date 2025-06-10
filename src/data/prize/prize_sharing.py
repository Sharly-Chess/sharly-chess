from abc import ABC, abstractmethod
from itertools import groupby
from typing import Tuple, override

from common.i18n import _
from data.player import Player
from data.prize.prize import Prize
from utils.entity import IdentifiableEntity


class PrizeSharing(IdentifiableEntity, ABC):
    """Class defining the way to share prizes when two or more
    players with the same points are eligible for prizes."""

    @abstractmethod
    def calculate_eligible_players(
        self,
        prizes: list[Prize],
        players: list[Player],
    ) -> list[Player]:
        """Returns all the players eligible to receive a prize"""

    @abstractmethod
    def resolve_prizes(
        self, prizes: list[Prize], players: list[Player]
    ) -> dict[int, Tuple[int, float]]:
        """Given a list of sorted players, returns a dict from player id to (place, prize_value)"""


class NoPrizeSharing(PrizeSharing):
    @staticmethod
    def static_id() -> str:
        return 'NONE'

    @staticmethod
    def static_name() -> str:
        return _('None')

    @override
    def calculate_eligible_players(
        self,
        prizes: list[Prize],
        players: list[Player],
    ) -> list[Player]:
        return players[: len(prizes)]

    @override
    def resolve_prizes(
        self, prizes: list[Prize], players: list[Player]
    ) -> dict[int, Tuple[int, float]]:
        resolved: dict[int, Tuple[int, float]] = {}
        for place, (player, prize) in enumerate(zip(players, prizes)):
            resolved[player.id] = (place, prize.value)
        return resolved


class AveragePrizeSharing(PrizeSharing):
    @staticmethod
    def static_id() -> str:
        return 'AVERAGE'

    @staticmethod
    def static_name() -> str:
        return _('Average')

    @override
    def calculate_eligible_players(
        self,
        prizes: list[Prize],
        players: list[Player],
    ) -> list[Player]:
        result: list[Player] = []
        prize_index = 0
        total_prizes = len(prizes)
        for score, group in groupby(players, key=lambda p: -(p.points or 0)):
            group_players = list(group)
            result.extend(group_players)
            prize_index += len(group_players)

            if prize_index >= total_prizes:
                break  # We've assigned enough prize "slots" to cover this last group

        return result

    @override
    def resolve_prizes(
        self, prizes: list[Prize], players: list[Player]
    ) -> dict[int, Tuple[int, float]]:
        resolved: dict[int, Tuple[int, float]] = {}
        num_distributed = 0
        place = 0
        for score, group in groupby(players, key=lambda p: p.points or 0):
            players_in_tie = list(group)
            prizes_to_share = prizes[
                num_distributed : num_distributed + len(players_in_tie)
            ]
            share = sum(p.value for p in prizes_to_share) / len(players_in_tie)
            for player in players_in_tie:
                resolved[player.id] = (place, share)

            place += 1
            num_distributed += len(players_in_tie)

        return resolved


class HortSystemPrizeSharing(PrizeSharing):
    @staticmethod
    def static_id() -> str:
        return 'HORT_SYSTEM'

    @staticmethod
    def static_name() -> str:
        return _('Hort system')

    @override
    def calculate_eligible_players(
        self,
        prizes: list[Prize],
        players: list[Player],
    ) -> list[Player]:
        result: list[Player] = []
        prize_index = 0
        total_prizes = len(prizes)
        for score, group in groupby(players, key=lambda p: -(p.points or 0)):
            group_players = list(group)
            result.extend(group_players)
            prize_index += len(group_players)

            if prize_index >= total_prizes:
                break  # We've assigned enough prize "slots" to cover this last group

        return result

    @override
    def resolve_prizes(
        self, prizes: list[Prize], players: list[Player]
    ) -> dict[int, Tuple[int, float]]:
        resolved: dict[int, Tuple[int, float]] = {}
        num_distributed = 0
        place = 0
        for score, group in groupby(players, key=lambda p: p.points or 0):
            players_in_tie = list(group)
            prizes_to_share = prizes[
                num_distributed : num_distributed + len(players_in_tie)
            ]
            total = sum(p.value for p in prizes_to_share)
            for i, player in enumerate(players_in_tie):
                own = prizes_to_share[i].value if i < len(prizes_to_share) else 0
                resolved[player.id] = (
                    place,
                    0.5 * own + 0.5 * (total / len(players_in_tie)),
                )
            place += 1
            num_distributed += len(players_in_tie)

        return resolved
