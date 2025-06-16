from data.prize.currencies import Currency
from data.prize import currencies
from data.prize.player_filter_options import PlayerFilterOption
from data.prize.player_filters import PlayerFilter
from data.prize.prize_sharing import (
    PrizeSharing,
    NoPrizeSharing,
    AveragePrizeSharing,
    HortSystemPrizeSharing,
)
from plugins.manager import plugin_manager
from utils.entity import EntityManager


class PlayerFilterManager(EntityManager[PlayerFilter]):
    @staticmethod
    def entity_types() -> list[type[PlayerFilter]]:
        from data.prize import player_filters as filters

        player_filters: list[type[PlayerFilter]] = [
            filters.GenderPlayerFilter,
            filters.RatingPlayerFilter,
            filters.AgePlayerFilter,
            filters.RatingTypePlayerFilter,
            filters.ClubPlayerFilter,
            filters.FederationPlayerFilter,
        ]
        plugin_manager.hook.insert_prize_player_filter_types(
            player_filter_types=player_filters
        )
        return player_filters


class PlayerFilterOptionManager(EntityManager[PlayerFilterOption]):
    @staticmethod
    def entity_types() -> list[type[PlayerFilterOption]]:
        from data.prize import player_filter_options as options

        filter_options: list[type[PlayerFilterOption]] = [
            options.GenderOption,
            options.MinRatingOption,
            options.MaxRatingOption,
            options.AgeCategoriesOption,
            options.AgeLowerOption,
            options.AgeGreaterOption,
            options.RatingTypesFilterOption,
            options.ClubsFilterOption,
            options.FederationsFilterOption,
        ]
        plugin_manager.hook.insert_prize_player_filter_option_types(
            player_filter_option_types=filter_options
        )
        return filter_options


class PrizeSharingManager(EntityManager[PrizeSharing]):
    @staticmethod
    def entity_types() -> list[type[PrizeSharing]]:
        return [
            NoPrizeSharing,
            AveragePrizeSharing,
            HortSystemPrizeSharing,
        ]


class CurrencyManager(EntityManager[Currency]):
    @staticmethod
    def entity_types() -> list[type[Currency]]:
        return [
            currencies.EuroCurrency,
            currencies.DollarCurrency,
            currencies.PoundSterlingCurrency,
        ]
