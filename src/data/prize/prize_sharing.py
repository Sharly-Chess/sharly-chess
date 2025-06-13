from abc import ABC, abstractmethod
from itertools import groupby
from typing import override

from common.i18n import _
from data.player import Player
from data.prize.prize import Prize
from data.prize.assigned_prize import AssignedPrize
from utils.entity import IdentifiableEntity


class PrizeSharing(IdentifiableEntity, ABC):
    """Class defining the way to share prizes when two or more
    players with the same points are eligible for prizes."""

    @abstractmethod
    def calculate_prizes(
        self,
        prizes: list[Prize],
        players: list[Player],
        threshold: float | None = None,
    ) -> list[AssignedPrize]:
        """Returns the prizes for each player"""


class NoPrizeSharing(PrizeSharing):
    @staticmethod
    def static_id() -> str:
        return 'NONE'

    @staticmethod
    def static_name() -> str:
        return _('None')

    @override
    def calculate_prizes(
        self,
        prizes: list[Prize],
        players: list[Player],
        threshold: float | None = None,
    ) -> list[AssignedPrize]:
        resolved: list[AssignedPrize] = []
        for place, (player, prize) in enumerate(zip(players, prizes)):
            resolved.append(
                AssignedPrize(
                    prize=prize,
                    priority=0,
                    place_index=place,
                    assigned_to=player,
                    value=prize.value,
                    is_main=True,
                )
            )
        return resolved


class AveragePrizeSharing(PrizeSharing):
    @staticmethod
    def static_id() -> str:
        return 'AVERAGE'

    @staticmethod
    def static_name() -> str:
        return _('Average')

    @override
    def calculate_prizes(
        self,
        prizes: list[Prize],
        players: list[Player],
        threshold: float | None = None,
    ) -> list[AssignedPrize]:
        resolved: list[AssignedPrize] = []
        place_index = 0
        total_prizes = len(prizes)
        warning = False
        for score, group in groupby(players, key=lambda p: -(p.points or 0)):
            players_in_tie = list(group)
            prizes_to_share = prizes[place_index : place_index + len(players_in_tie)]
            total = sum(p.value for p in prizes_to_share)
            share = total / len(players_in_tie)
            if threshold is not None:
                while share < threshold and players_in_tie:
                    players_in_tie.pop()
                    share = total / len(players_in_tie)
                    warning = True
            for i, player in enumerate(players_in_tie):
                is_last = i == len(players_in_tie) - 1
                resolved.append(
                    AssignedPrize(
                        prize=prizes_to_share[0],
                        priority=0,
                        place_index=place_index,
                        assigned_to=player,
                        value=share,
                        is_main=True,
                        warning=_(
                            'Other players in this score group are not included since the share would be less than the threshold.'
                        )
                        if is_last and warning
                        else None,
                    )
                )

            place_index += len(players_in_tie)

            if place_index >= total_prizes:
                break  # We've assigned enough prize "slots" to cover this last group

        return resolved


class HortSystemPrizeSharing(PrizeSharing):
    @staticmethod
    def static_id() -> str:
        return 'HORT_SYSTEM'

    @staticmethod
    def static_name() -> str:
        return _('Hort system')

    @override
    def calculate_prizes(
        self,
        prizes: list[Prize],
        players: list[Player],
        threshold: float | None = None,
    ) -> list[AssignedPrize]:
        resolved: list[AssignedPrize] = []
        place_index = 0
        total_prizes = len(prizes)
        warning = False
        for score, group in groupby(players, key=lambda p: -(p.points or 0)):
            players_in_tie = list(group)
            prizes_to_share = prizes[place_index : place_index + len(players_in_tie)]
            total = sum(p.value for p in prizes_to_share)

            if threshold is not None:
                # The only way to have a share with less than the threshold is to have more players than prizes
                while (
                    len(players_in_tie) > len(prizes_to_share)
                    and total / len(players_in_tie) / 2 < threshold
                    and players_in_tie
                ):
                    warning = True
                    players_in_tie.pop()

            for i, player in enumerate(players_in_tie):
                own = prizes_to_share[i].value if i < len(prizes_to_share) else 0
                is_last = i == len(players_in_tie) - 1
                resolved.append(
                    AssignedPrize(
                        prize=prizes_to_share[0],
                        priority=0,
                        place_index=place_index,
                        assigned_to=player,
                        value=(own + total / len(players_in_tie)) / 2,
                        is_main=True,
                        warning=_(
                            'Other players in this score group are not included since the share would be less than the threshold.'
                        )
                        if is_last and warning
                        else None,
                    )
                )

            place_index += len(players_in_tie)

            if place_index >= total_prizes:
                break  # We've assigned enough prize "slots" to cover this last group

        return resolved
