from data.prize.player_filter_options import PlayerFilterOption
from data.prize.player_filters import PlayerFilter
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
        from data.prize import player_filters as filters

        return [
            filters.GenderPlayerFilter,
            filters.RatingPlayerFilter,
            filters.AgePlayerFilter,
        ]


class PlayerFilterOptionManager(EntityManager[PlayerFilterOption]):
    @staticmethod
    def entity_types() -> list[type[PlayerFilterOption]]:
        from data.prize import player_filter_options as options

        return [
            options.GenderOption,
            options.MinRatingOption,
            options.MaxRatingOption,
            options.AgeCategoriesOption,
            options.AgeLowerOption,
            options.AgeGreaterOption,
        ]


class PrizeSharingManager(EntityManager[PrizeSharing]):
    @staticmethod
    def entity_types() -> list[type[PrizeSharing]]:
        return [
            NoPrizeSharing,
            AveragePrizeSharing,
            HortSystemPrizeSharing,
        ]
