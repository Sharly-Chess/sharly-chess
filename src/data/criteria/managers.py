from typing import TYPE_CHECKING, Optional, override
from common.sharly_chess_config import SharlyChessConfig
from data.criteria.player_filter_options import PlayerFilterOption
from data.criteria.player_filters import PlayerFilter
from data.criteria import tournament_criteria as crit
from data.criteria.tournament_criteria import TournamentCriterion
from plugins.manager import plugin_manager
from utils.entity import EventBoundEntityManager
from utils.enum import PlayerGender

if TYPE_CHECKING:
    from data.event import Event


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


class SearchFilterManager:
    def __init__(self, event: Optional['Event']):
        self.event = event

    def get_filters(self) -> list[dict]:
        federations = {'': '-'} | {
            federation_id: f'{federation_id} - {federation_name}'
            for federation_id, federation_name in SharlyChessConfig().federations.items()
        }
        if 'NON' in federations:
            del federations['NON']

        categories = self.event.player_categories
        del categories[0]

        filters = {
            'federation': {
                'template_name': 'search_filters/federation.html',
                'options': federations,
            },
            'gender': {
                'template_name': 'search_filters/gender.html',
                'options': {gender: gender.name for gender in PlayerGender},
            },
            'category': {
                'template_name': 'search_filters/category.html',
                'options': {category.id: category.name for category in categories},
            },
            'club': {
                'template_name': 'search_filters/club.html',
            },
        }
        plugin_manager.hook_for_event(self.event, 'insert_search_filter_types')(
            filters=filters
        )

        return filters
