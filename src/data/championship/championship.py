from datetime import date
from functools import cached_property
from logging import Logger
from typing import TYPE_CHECKING, cast

from common.logger import get_logger
from database.sqlite.championship.championship_store import (
    StoredChampionship,
    StoredChampionshipSource,
)

if TYPE_CHECKING:
    from data.event import Event
    from data.championship.category import ChampionshipCategory
    from data.championship.reconciliation import ReconciledPlayer, ReconciledTeam
    from data.championship.scoring import ChampionshipRule
    from data.tournament import Tournament


class RankingEntry:
    """One line of the championship ranking. ``tied`` is true when the player
    shares its rank with others no rule could separate."""

    def __init__(
        self,
        rank: int,
        competitor: 'ReconciledPlayer | ReconciledTeam',
        tied: bool,
    ):
        self.rank: int = rank
        self.competitor = competitor
        # Backward compatibility for individual GP consumers.
        self.player = competitor
        self.tied: bool = tied


logger: Logger = get_logger()


class ChampionshipSource:
    """A referenced tournament resolved against the live events on disk.

    ``tournament`` is ``None`` when the reference is broken (the event or the
    tournament no longer exists); ``broken_reason`` then explains why and the
    snapshot fields on the stored source provide a readable label."""

    def __init__(
        self,
        stored_source: StoredChampionshipSource,
        event: 'Event | None',
        tournament: 'Tournament | None',
        broken_reason: str | None,
    ):
        self.stored_source: StoredChampionshipSource = stored_source
        self.event: 'Event | None' = event
        self.tournament: 'Tournament | None' = tournament
        self.broken_reason: str | None = broken_reason

    @property
    def id(self) -> int:
        assert self.stored_source.id is not None
        return self.stored_source.id

    @property
    def broken(self) -> bool:
        return self.tournament is None

    @property
    def event_openable(self) -> bool:
        """Whether the source event can be opened in the admin: it exists and
        all the plugins it requires are enabled (mirrors the events list)."""
        if self.event is None:
            return False
        return all(plugin.is_enabled for plugin in self.event.enabled_plugins)

    @property
    def event_uniq_id(self) -> str:
        return self.stored_source.event_uniq_id

    @property
    def tournament_id(self) -> int:
        return self.stored_source.tournament_id

    @property
    def coefficient(self) -> float:
        return self.stored_source.coefficient

    @property
    def event_name(self) -> str:
        if self.event is not None:
            return self.event.name
        return self.stored_source.event_name or self.stored_source.event_uniq_id

    @property
    def tournament_name(self) -> str:
        if self.tournament is not None:
            return self.tournament.name
        return self.stored_source.tournament_name or str(
            self.stored_source.tournament_id
        )

    @property
    def start_date(self) -> date | None:
        if self.tournament is not None:
            return self.tournament.start_date
        return self.stored_source.start_date

    @property
    def stop_date(self) -> date | None:
        if self.tournament is not None:
            return self.tournament.stop_date
        return self.stored_source.stop_date or self.stored_source.start_date


class Championship:
    """A championship: an aggregate ranking built from tournaments belonging to
    independent events. It owns no tournaments of its own — it references them
    and reads their results live."""

    def __init__(self, stored_championship: StoredChampionship, uniq_id: str):
        self.stored_championship: StoredChampionship = stored_championship
        self.uniq_id: str = uniq_id

    @property
    def name(self) -> str:
        return self.stored_championship.name

    @property
    def age_category_base_date(self) -> date | None:
        return self.stored_championship.age_category_base_date

    @property
    def default_age_category_base_date(self) -> date | None:
        """The automatic reference date: 1 January of the first source
        tournament's year."""
        source_dates = [
            source.start_date for source in self.sources if source.start_date
        ]
        if not source_dates:
            return None
        return date(min(source_dates).year, 1, 1)

    @property
    def effective_age_category_base_date(self) -> date | None:
        return self.age_category_base_date or self.default_age_category_base_date

    @property
    def start_date(self) -> date | None:
        source_dates = [
            source.start_date for source in self.sources if source.start_date
        ]
        return min(source_dates) if source_dates else None

    @property
    def stop_date(self) -> date | None:
        source_dates = [source.stop_date for source in self.sources if source.stop_date]
        return max(source_dates) if source_dates else self.start_date

    @property
    def coming(self) -> bool:
        """Starts in the future (matches the home-page classification)."""
        return self.start_date is not None and date.today() < self.start_date

    @property
    def passed(self) -> bool:
        """Already finished (matches the home-page classification)."""
        return self.stop_date is not None and self.stop_date < date.today()

    @property
    def competitor_type(self):
        from data.championship.options import ChampionshipCompetitorType

        return ChampionshipCompetitorType(self.stored_championship.competitor_type)

    @property
    def team_score_basis(self):
        from data.championship.options import TeamScoreBasis

        return TeamScoreBasis(self.stored_championship.team_score_basis)

    @cached_property
    def sources(self) -> list[ChampionshipSource]:
        """Resolve every stored source against the events on disk, loading each
        distinct event only once. Broken references are kept (not dropped) so
        the caller can surface them."""
        from data.event import Event
        from data.loader import EventLoader
        from database.sqlite.event.event_database import EventDatabase

        event_loader = EventLoader()
        events_by_uniq_id: dict[str, Event | None] = {}

        sources: list[ChampionshipSource] = []
        for stored_source in self.stored_championship.stored_sources:
            event_uniq_id = stored_source.event_uniq_id
            if event_uniq_id not in events_by_uniq_id:
                events_by_uniq_id[event_uniq_id] = None
                if EventDatabase.event_database_path(event_uniq_id).exists():
                    try:
                        events_by_uniq_id[event_uniq_id] = event_loader.load_event(
                            event_uniq_id
                        )
                    except Exception as error:
                        logger.warning(
                            'Championship [%s]: could not load event [%s]: %s',
                            self.uniq_id,
                            event_uniq_id,
                            error,
                        )

            event = events_by_uniq_id[event_uniq_id]
            tournament = None
            broken_reason: str | None = None
            if event is None:
                broken_reason = 'event_not_found'
            else:
                tournament = event.tournaments_by_id.get(stored_source.tournament_id)
                if tournament is None:
                    broken_reason = 'tournament_not_found'
                else:
                    from data.championship.options import ChampionshipCompetitorType

                    source_type = (
                        ChampionshipCompetitorType.TEAM
                        if event.is_team_event
                        else ChampionshipCompetitorType.INDIVIDUAL
                    )
                    if source_type != self.competitor_type:
                        tournament = None
                        broken_reason = 'competitor_type_mismatch'
            sources.append(
                ChampionshipSource(stored_source, event, tournament, broken_reason)
            )
        return sorted(
            sources,
            key=lambda source: (
                source.start_date is None,
                source.start_date or date.max,
            ),
        )

    @property
    def broken_sources(self) -> list[ChampionshipSource]:
        return [source for source in self.sources if source.broken]

    @cached_property
    def _overrides_by_ref(self) -> dict[tuple[str, int, int], str]:
        return {
            (
                override.event_uniq_id,
                override.tournament_id,
                override.source_player_id,
            ): override.group_key
            for override in self.stored_championship.stored_player_overrides
        }

    @cached_property
    def _team_overrides_by_ref(self) -> dict[tuple[str, int, int], str]:
        return {
            (
                override.event_uniq_id,
                override.tournament_id,
                override.source_team_id,
            ): override.group_key
            for override in self.stored_championship.stored_team_overrides
        }

    @cached_property
    def players(self) -> list['ReconciledPlayer']:
        """The distinct humans across all sources, matched live by identity and
        manual overrides. Recomputed on load (sources are read live)."""
        from data.championship.options import ChampionshipCompetitorType
        from data.championship.reconciliation import reconcile_players

        if self.competitor_type != ChampionshipCompetitorType.INDIVIDUAL:
            raise RuntimeError('A team championship has teams, not ranked players')
        return reconcile_players(self.sources, self._overrides_by_ref)

    @cached_property
    def teams(self) -> list['ReconciledTeam']:
        from data.championship.options import ChampionshipCompetitorType
        from data.championship.reconciliation import reconcile_teams

        if self.competitor_type != ChampionshipCompetitorType.TEAM:
            raise RuntimeError(
                'An individual championship has players, not ranked teams'
            )
        return reconcile_teams(self.sources, self._team_overrides_by_ref)

    @cached_property
    def competitors(self) -> list['ReconciledPlayer | ReconciledTeam']:
        from data.championship.options import ChampionshipCompetitorType

        if self.competitor_type == ChampionshipCompetitorType.TEAM:
            return cast(list['ReconciledPlayer | ReconciledTeam'], self.teams)
        return cast(list['ReconciledPlayer | ReconciledTeam'], self.players)

    @cached_property
    def rules(self) -> list['ChampionshipRule']:
        from data.championship.scoring import build_rule

        return [
            build_rule(stored_rule.type, stored_rule.best_n, stored_rule.options)
            for stored_rule in sorted(
                self.stored_championship.stored_championship_rules,
                key=lambda stored_rule: stored_rule.index,
            )
        ]

    @cached_property
    def categories(self) -> list['ChampionshipCategory']:
        from data.championship.category import ChampionshipCategory
        from data.championship.options import ChampionshipCompetitorType

        if self.competitor_type == ChampionshipCompetitorType.TEAM:
            return []

        return [
            ChampionshipCategory(self, stored_category)
            for stored_category in sorted(
                self.stored_championship.stored_championship_categories,
                key=lambda category: category.index,
            )
        ]

    @property
    def manual_positions(self) -> dict[str, int]:
        return dict(self.stored_championship.stored_manual_tiebreaks)

    @cached_property
    def has_manual_rule(self) -> bool:
        from data.championship.scoring import ManualRule

        return any(isinstance(rule, ManualRule) for rule in self.rules)

    def _rules_before_manual(self) -> list['ChampionshipRule']:
        from data.championship.scoring import ManualRule

        rules: list['ChampionshipRule'] = []
        for rule in self.rules:
            if isinstance(rule, ManualRule):
                break
            rules.append(rule)
        return rules

    def manual_tie_groups(
        self, competitors: list['ReconciledPlayer | ReconciledTeam']
    ) -> list[list['ReconciledPlayer | ReconciledTeam']]:
        """Ordered tie groups formed by the rules that run before the manual
        tie-break — the groups within which competitors may be dragged."""
        from data.championship.scoring import rank_competitors

        return rank_competitors(
            competitors,
            self._rules_before_manual(),
            self.team_score_basis,
        )

    def build_ranking(
        self, competitors: list['ReconciledPlayer | ReconciledTeam']
    ) -> list[RankingEntry]:
        """Rank an arbitrary eligible player set with this GP's rules."""
        from data.championship.scoring import rank_competitors

        entries: list[RankingEntry] = []
        rank = 1
        for group in rank_competitors(
            competitors,
            self.rules,
            self.team_score_basis,
            self.manual_positions,
        ):
            tied = len(group) > 1
            for competitor in group:
                entries.append(RankingEntry(rank, competitor, tied))
            rank += len(group)
        return entries

    @cached_property
    def ranking(self) -> list[RankingEntry]:
        """The championship standings: reconciled players ordered by the rule
        list, with tied players sharing a rank (1, 2, 2, 4, ...)."""
        return self.build_ranking(self.competitors)
