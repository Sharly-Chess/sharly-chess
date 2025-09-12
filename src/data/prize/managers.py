from data.prize.prize_sharing import (
    PrizeSharing,
    NoPrizeSharing,
    AveragePrizeSharing,
    HortSystemPrizeSharing,
)
from utils.entity import EntityManager


class PrizeSharingManager(EntityManager[PrizeSharing]):
    @staticmethod
    def entity_types() -> list[type[PrizeSharing]]:
        return [
            NoPrizeSharing,
            AveragePrizeSharing,
            HortSystemPrizeSharing,
        ]
