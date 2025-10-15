from typing import override
from data.prize.prize_sharing import (
    PrizeSharing,
    NoPrizeSharing,
    AveragePrizeSharing,
    HortSystemPrizeSharing,
)
from utils.entity import EntityManager


class PrizeSharingManager(EntityManager[PrizeSharing]):
    @override
    def entity_types(self) -> list[type[PrizeSharing]]:
        return [
            NoPrizeSharing,
            AveragePrizeSharing,
            HortSystemPrizeSharing,
        ]
