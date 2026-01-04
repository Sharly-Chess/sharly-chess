from data.prize.prize_sharing import (
    PrizeSharing,
    NoPrizeSharing,
    AveragePrizeSharing,
    HortSystemPrizeSharing,
)
from data.prize.prize_type import (
    PrizeType,
    MonetaryPrizeType,
    NonMonetaryPrizeType,
    HybridPrizeType,
)
from utils.entity import EntityManager


class PrizeSharingManager(EntityManager[PrizeSharing]):
    def entity_types(self) -> list[type[PrizeSharing]]:
        return [
            NoPrizeSharing,
            AveragePrizeSharing,
            HortSystemPrizeSharing,
        ]


class PrizeTypeManager(EntityManager[PrizeType]):
    def entity_types(self) -> list[type[PrizeType]]:
        return [
            MonetaryPrizeType,
            NonMonetaryPrizeType,
            HybridPrizeType,
        ]
