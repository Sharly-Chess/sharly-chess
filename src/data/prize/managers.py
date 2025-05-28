from data.prize.player_filter_options import (
    PlayerFilterOption,
    GenderPlayerFilterOption,
)
from data.prize.player_filters import PlayerFilter, GenderPlayerFilter
from data.prize.prize_sharing import (
    PrizeSharing,
    NoPrizeSharing,
    AveragePrizeSharing,
    HortSystemPrizeSharing,
)
from utils.entity import EntityManager


class PlayerFilterManager(EntityManager[PlayerFilter]):
    @staticmethod
    def entity_types() -> list[type[PlayerFilter]]:
        return [GenderPlayerFilter]


class PlayerFilterOptionManager(EntityManager[PlayerFilterOption]):
    @staticmethod
    def entity_types() -> list[type[PlayerFilterOption]]:
        return [GenderPlayerFilterOption]


class PrizeSharingManager(EntityManager[PrizeSharing]):
    @staticmethod
    def entity_types() -> list[type[PrizeSharing]]:
        return [
            NoPrizeSharing,
            AveragePrizeSharing,
            HortSystemPrizeSharing,
        ]
