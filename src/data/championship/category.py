"""Filtered category standings for a Championship."""

import weakref
from functools import cached_property
from logging import Logger
from typing import TYPE_CHECKING, cast

from common.logger import get_logger
from data.criteria.managers import PrizePlayerFilterManager
from data.championship.reconciliation import ReconciledPlayer
from data.player_categories import NoCategory, PlayerCategory

if TYPE_CHECKING:
    from data.championship.championship import Championship, RankingEntry
    from data.championship.reconciliation import ReconciledParticipation
    from database.sqlite.championship.championship_store import (
        StoredChampionshipCategory,
        StoredChampionshipCriterion,
    )

logger: Logger = get_logger()


class ChampionshipCriterion:
    """A prize-filter-compatible criterion applied to a GP participation."""

    def __init__(self, stored_criterion: 'StoredChampionshipCriterion'):
        self.stored_criterion = stored_criterion

    @property
    def type(self) -> str:
        return self.stored_criterion.type

    @property
    def options(self) -> dict:
        return self.stored_criterion.options

    def _matches_age(self, category: PlayerCategory) -> bool:
        if category == NoCategory():
            return False
        min_id = self.options.get('MIN_AGE_CATEGORY')
        max_id = self.options.get('MAX_AGE_CATEGORY')
        min_category = PlayerCategory.from_id(min_id) if min_id else None
        max_category = PlayerCategory.from_id(max_id) if max_id else None
        if min_category is not None and category < min_category:
            return False
        if max_category is not None and category > max_category:
            return False
        return min_category is not None or max_category is not None

    def matches(
        self,
        participation: 'ReconciledParticipation',
        player_category: PlayerCategory | None = None,
    ) -> bool:
        tournament_player = participation.tournament_player
        if self.type == 'AGE':
            return self._matches_age(player_category or tournament_player.category)

        event = participation.source.event
        if event is None:
            return False
        try:
            filter_type = PrizePlayerFilterManager(event).get_type(self.type)
        except KeyError:
            logger.warning(
                'Championship criterion [%s] is not available for event [%s].',
                self.type,
                participation.event_uniq_id,
            )
            return False
        options = [
            option_type(
                self.options.get(option_type.static_id(), option_type().default_value)
            )
            for option_type in filter_type.available_options()
        ]
        return filter_type(options).is_player_included_function(tournament_player)


class ChampionshipCategory:
    """One named standings view, filtered by all of its criteria."""

    def __init__(
        self,
        championship: 'Championship',
        stored_category: 'StoredChampionshipCategory',
    ):
        self._championship_ref = weakref.ref(championship)
        self.stored_category = stored_category

    @property
    def championship(self) -> 'Championship':
        if (championship := self._championship_ref()) is None:
            raise RuntimeError('Reference has been garbage collected')
        return championship

    @property
    def id(self) -> int:
        assert self.stored_category.id is not None
        return self.stored_category.id

    @property
    def name(self) -> str:
        return self.stored_category.name

    @cached_property
    def criteria(self) -> list[ChampionshipCriterion]:
        return [
            ChampionshipCriterion(stored_criterion)
            for stored_criterion in self.stored_category.stored_criteria
        ]

    def _matches(
        self,
        participation: 'ReconciledParticipation',
        player_category: PlayerCategory,
    ) -> bool:
        return all(
            criterion.matches(participation, player_category)
            for criterion in self.criteria
        )

    @staticmethod
    def _reference_participation(
        player: ReconciledPlayer,
    ) -> 'ReconciledParticipation':
        def start_date(participation: 'ReconciledParticipation'):
            tournament = participation.source.tournament
            assert tournament is not None
            return tournament.start_date

        return min(player.participations, key=start_date)

    def _player_category(
        self,
        player: ReconciledPlayer,
        participation: 'ReconciledParticipation',
    ) -> PlayerCategory:
        reference_date = self.championship.effective_age_category_base_date
        event = participation.source.event
        if reference_date is None or event is None:
            return NoCategory()
        return PlayerCategory.from_year_of_birth_at_date(
            event,
            player.year_of_birth,
            reference_date,
        )

    @cached_property
    def players(self) -> list[ReconciledPlayer]:
        """Eligible players classified once for the whole Championship."""
        if not self.criteria:
            return self.championship.players

        players: list[ReconciledPlayer] = []
        for player in self.championship.players:
            reference = self._reference_participation(player)
            player_category = self._player_category(player, reference)
            if self._matches(reference, player_category):
                players.append(player)
        return players

    @cached_property
    def ranking(self) -> list['RankingEntry']:
        from data.championship.reconciliation import ReconciledTeam

        return self.championship.build_ranking(
            cast(list[ReconciledPlayer | ReconciledTeam], self.players)
        )
