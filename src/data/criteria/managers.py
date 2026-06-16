from typing import override
from data.criteria.player_filter_options import PlayerFilterOption
from data.criteria.player_filters import PlayerFilter
from data.criteria import tournament_criteria as crit
from data.criteria.tournament_criteria import TournamentCriterion
from plugins.manager import plugin_manager
from utils.entity import EventBoundEntityManager


class PrizePlayerFilterManager(EventBoundEntityManager[PlayerFilter]):
    def entity_types(self) -> list[type[PlayerFilter]]:
        from data.criteria import player_filters as filters

        player_filters: list[type[PlayerFilter]] = [
            filters.GenderPlayerFilter,
            filters.RatingPlayerFilter,
            filters.AgePlayerFilter,
            filters.RatingTypePlayerFilter,
            filters.ClubPlayerFilter,
            filters.FederationPlayerFilter,
            filters.CommentPlayerFilter,
            filters.PlayerIdPlayerFilter,
        ]
        plugin_manager.hook_for_event(self.event, 'insert_player_filter_types')(
            player_filter_types=player_filters
        )
        return player_filters


class PlayerFilterOptionManager(EventBoundEntityManager[PlayerFilterOption]):
    @override
    def entity_types(self) -> list[type[PlayerFilterOption]]:
        from data.criteria import player_filter_options as options

        filter_options: list[type[PlayerFilterOption]] = [
            options.GenderOption,
            options.MinRatingOption,
            options.MaxRatingOption,
            options.MinAgeCategoryOption,
            options.MaxAgeCategoryOption,
            options.RatingTypesFilterOption,
            options.ClubsFilterOption,
            options.FederationsFilterOption,
            options.CommentsFilterOption,
            options.PlayersFilterOption,
            options.ExcludeFilterOption,
        ]
        plugin_manager.hook_for_event(self.event, 'insert_player_filter_option_types')(
            player_filter_option_types=filter_options
        )
        return filter_options


class TournamentCriterionManager(EventBoundEntityManager[TournamentCriterion]):
    def entity_types(self) -> list[type[TournamentCriterion]]:
        criteria: list[type[TournamentCriterion]] = [
            crit.RatingTournamentCriterion,
            crit.AgeCategoryTournamentCriterion,
            crit.GenderTournamentCriterion,
            crit.ClubTournamentCriterion,
            crit.FederationTournamentCriterion,
        ]
        plugin_manager.hook_for_event(self.event, 'insert_tournament_criteria_types')(
            criteria_types=criteria
        )
        return criteria
