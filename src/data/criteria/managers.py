from abc import ABC
from typing import override
from data.criteria.player_filter_options import PlayerFilterOption
from data.criteria.player_filters import PlayerFilter
from plugins.manager import plugin_manager
from utils.entity import EventBoundEntityManager


class PlayerFilterManager(EventBoundEntityManager[PlayerFilter], ABC):
    def entity_types(self) -> list[type[PlayerFilter]]:
        from data.criteria import player_filters as filters

        player_filters: list[type[PlayerFilter]] = [
            filters.GenderPlayerFilter,
            filters.RatingPlayerFilter,
            filters.AgePlayerFilter,
            filters.RatingTypePlayerFilter,
            filters.ClubPlayerFilter,
            filters.FederationPlayerFilter,
        ]
        plugin_manager.hook_for_event(self.event, 'insert_player_filter_types')(
            player_filter_types=player_filters
        )
        return player_filters


class TournamentPlayerFilterManager(PlayerFilterManager):
    """Player filters used for tournament criteria."""


class PrizePlayerFilterManager(PlayerFilterManager):
    """Player filters used for prize criteria."""

    @override
    def entity_types(self) -> list[type[PlayerFilter]]:
        from data.criteria import player_filters as filters

        return super().entity_types() + [filters.PlayerIdPlayerFilter]


class PlayerFilterOptionManager(EventBoundEntityManager[PlayerFilterOption]):
    @override
    def entity_types(self) -> list[type[PlayerFilterOption]]:
        from data.criteria import player_filter_options as options

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
            options.PlayersPlayerFilterOption,
        ]
        plugin_manager.hook_for_event(self.event, 'insert_player_filter_option_types')(
            player_filter_option_types=filter_options
        )
        return filter_options
