"""Championship scoring for a championship.

An ordered list of rules ranks the reconciled competitors. The ranking is built by
successive refinement: everyone starts in one tie group, each rule in turn
splits the groups that are still tied, and later rules only ever break ties the
earlier ones left. This lets a scalar rule (total points, win count) and a
pairwise rule (direct encounter) be mixed in any order — which is what real
regulations do (e.g. total points -> wins -> direct encounter -> total points
over more stages).

Rules scoped to a competitor's "best N" stages select those stages by the same
ordered rule chain that ranks the competitors (each rule's per-stage value), and
that selection is shared across rules: "wins over the best 4 stages" counts wins
on the 4 stages the chain rates highest, not the 4 stages with the most wins."""

import inspect
import json
from abc import ABC, abstractmethod
from collections import defaultdict
from statistics import fmean
from typing import TYPE_CHECKING, TypeAlias, cast

from common.i18n import _
from data.championship.options import TeamScoreBasis

if TYPE_CHECKING:
    from data.championship.reconciliation import (
        ReconciledParticipation,
        ReconciledPlayer,
        ReconciledTeam,
        ReconciledTeamParticipation,
    )
    from data.tie_breaks.tie_breaks import TieBreak

    ReconciledCompetitor: TypeAlias = ReconciledPlayer | ReconciledTeam
    CompetitorParticipation: TypeAlias = (
        ReconciledParticipation | ReconciledTeamParticipation
    )


def participation_points(
    participation: 'CompetitorParticipation',
    team_score_basis: TeamScoreBasis,
    use_coefficient: bool = True,
) -> float:
    """A stage's points for scoring: the raw source points, weighted by the
    stage coefficient unless ``use_coefficient`` is off (a stage may count more
    than once)."""
    base = participation.points(team_score_basis)
    return base * participation.coefficient if use_coefficient else base


def participation_wins(participation: 'CompetitorParticipation') -> int:
    return participation.wins


def scaled_stage_value(
    participation: 'CompetitorParticipation', use_coefficient: bool = True
) -> float:
    """A stage rescaled so the winner scores 1 and the last-placed 0, weighted
    by the stage coefficient unless ``use_coefficient`` is off. 0 for an
    unranked or single-competitor stage."""
    field_size = participation.field_size
    if field_size <= 1 or not participation.rank:
        return 0.0
    scaled = (field_size - participation.rank) / (field_size - 1)
    return scaled * participation.coefficient if use_coefficient else scaled


def _stage_selection_key(
    participation: 'CompetitorParticipation',
    team_score_basis: TeamScoreBasis,
    context: 'ScoringContext | None' = None,
) -> tuple[float, ...]:
    """Ascending sort key for choosing best stages (smaller = better).

    The "best N" is chosen by the championship's own configured rule chain
    applied per stage (each rule's ``stage_value``, in order), so a competitor's
    best stages are the ones where they performed best by exactly the criteria
    that rank them. Falls back to a fixed points/wins/position cascade when no
    per-stage rule is configured."""
    weighted_points = participation.weighted_points(team_score_basis)
    if context is not None:
        stage_values = [
            value
            for value in (
                rule.stage_value(participation, context) for rule in context.rules
            )
            if value is not None
        ]
        if stage_values:
            return tuple(-value for value in stage_values)
    # No per-stage rule configured: a sensible intrinsic cascade. Lower
    # finishing position is better; unranked sorts last.
    rank = float(participation.rank) if participation.rank else float('inf')
    return (-weighted_points, -float(participation.wins), rank)


def best_participations(
    competitor: 'ReconciledCompetitor',
    best_n: int | None,
    team_score_basis: TeamScoreBasis = TeamScoreBasis.SOURCE_PRIMARY,
    context: 'ScoringContext | None' = None,
) -> list['CompetitorParticipation']:
    """The competitor's best ``best_n`` participations, chosen by the configured
    rule chain (see :func:`_stage_selection_key`). Shared across rules, so every
    rule reads the same subset."""
    ordered = sorted(
        competitor.participations,
        key=lambda participation: _stage_selection_key(
            participation, team_score_basis, context
        ),
    )
    selected = ordered if best_n is None else ordered[:best_n]
    return cast(list['CompetitorParticipation'], selected)


class ScoringContext:
    """Shared state for a ranking pass: the reconciled players, a lookup from a
    source pairing's opponent to the reconciled player, and the per-tournament
    rank computation (needed so ``points`` is populated)."""

    def __init__(
        self,
        competitors: list['ReconciledCompetitor'],
        team_score_basis: TeamScoreBasis = TeamScoreBasis.SOURCE_PRIMARY,
        manual_positions: dict[str, int] | None = None,
        rules: list['ChampionshipRule'] | None = None,
    ):
        self.competitors = competitors
        self.team_score_basis = team_score_basis
        # Manual tie-break: competitor key -> pinned position (higher = better).
        self.manual_positions = manual_positions or {}
        # The configured rule chain, used to break best-stage selection ties by
        # the same criteria the championship ranks competitors by.
        self.rules = rules or []
        self._competitor_by_ref: dict[tuple[str, int, int], 'ReconciledCompetitor'] = {}
        # Cache of computed source tie-break values, per (tournament, type,
        # options): a tie-break is computed once for a whole source tournament,
        # not per competitor per rule.
        self._tie_break_cache: dict[tuple[int, str, str], dict[int, float]] = {}
        # Cache of the tie-break *instance* per (type, options): built once from
        # a source event that offers it, then reused to compute against every
        # source tournament (see tie_break_value).
        self._tie_break_instances: dict[tuple[str, str], object] = {}
        computed: set[int] = set()
        for competitor in competitors:
            for participation in competitor.participations:
                self._competitor_by_ref[
                    (
                        participation.event_uniq_id,
                        participation.tournament_id,
                        participation.source_competitor_id,
                    )
                ] = competitor
                tournament = participation.source.tournament
                if (
                    hasattr(participation, 'tournament_player')
                    and tournament is not None
                    and id(tournament) not in computed
                ):
                    tournament.ensure_tournament_player_ranks_computed()
                    computed.add(id(tournament))

    def competitor_for_opponent(
        self, participation: 'CompetitorParticipation', opponent_id: int
    ) -> 'ReconciledCompetitor | None':
        return self._competitor_by_ref.get(
            (participation.event_uniq_id, participation.tournament_id, opponent_id)
        )

    def tie_break_value(
        self, participation: 'CompetitorParticipation', type_id: str, options: dict
    ) -> float | None:
        """This participation's value for the given tie-break, COMPUTED from the
        source tournament's game data.

        The tie-break's plugin only supplies the *algorithm*; the value (e.g.
        Buchholz) is computed from the games, so we compute it for EVERY source
        even ones whose event does not enable that plugin — the stage is not
        skipped. ``None`` only when the tie-break cannot be resolved at all, is
        not a per-player value, or the competitor is a team (not supported yet).
        """
        if not hasattr(participation, 'tournament_player'):
            return None
        tournament = participation.source.tournament
        if tournament is None:
            return None
        tie_break = self._resolve_tie_break(type_id, options)
        if tie_break is None or not tie_break.is_computed_per_player:
            return None
        signature = json.dumps(options, sort_keys=True, default=str)
        cache_key = (id(tournament), type_id, signature)
        if cache_key not in self._tie_break_cache:
            self._tie_break_cache[cache_key] = self._compute_values(
                tie_break, tournament
            )
        return self._tie_break_cache[cache_key].get(participation.source_competitor_id)

    def _resolve_tie_break(self, type_id: str, options: dict):
        """Build the tie-break instance once, from whichever source event offers
        it (there is at least one — that is why it was offered). The instance is
        not bound to that tournament, so it computes for any source."""
        signature = json.dumps(options, sort_keys=True, default=str)
        cache_id = (type_id, signature)
        if cache_id in self._tie_break_instances:
            return self._tie_break_instances[cache_id]

        from database.sqlite.event.event_store import StoredTieBreak
        from data.tie_breaks.sets import instantiate_tie_break

        instance = None
        seen_events: set[str] = set()
        for competitor in self.competitors:
            for participation in competitor.participations:
                source = participation.source
                event = getattr(source, 'event', None)
                tournament = getattr(source, 'tournament', None)
                if event is None or tournament is None:
                    continue
                if source.event_uniq_id in seen_events:
                    continue
                seen_events.add(source.event_uniq_id)
                instance = instantiate_tie_break(
                    StoredTieBreak(
                        id=None,
                        tournament_id=tournament.id,
                        type=type_id,
                        options=dict(options),
                        index=0,
                    ),
                    event,
                )
                if instance is not None:
                    break
            if instance is not None:
                break
        self._tie_break_instances[cache_id] = instance
        return instance

    @staticmethod
    def _compute_values(tie_break, tournament) -> dict:
        """Compute a per-player tie-break for every player of ``tournament``."""
        after_round = tournament.max_ranking_round
        values: dict[int, float] = {}
        for player in tournament.tournament_players:
            try:
                values[player.id] = float(
                    tie_break.compute_player_value(player, after_round=after_round)
                )
            except Exception:
                return {}
        return values


def _split_by_value(group, value_fn, *, reverse=True):
    """Order a group by a scalar value and split it into subgroups of equal
    value (rounded, to absorb float noise), best first."""
    valued = sorted(group, key=value_fn, reverse=reverse)
    subgroups: list[list] = []
    current: list = []
    current_key = None
    for player in valued:
        key = round(value_fn(player), 6)
        if current and key != current_key:
            subgroups.append(current)
            current = []
        current.append(player)
        current_key = key
    if current:
        subgroups.append(current)
    return subgroups


class ChampionshipRule(ABC):
    """A championship scoring criterion.

    Each concrete rule owns its identity (``static_id``), display metadata
    (``base_acronym`` / ``label`` / ``description``) and behaviour, mirroring
    the tournament tie-break framework — there is no separate rule-type enum.
    New rules are discovered automatically through :func:`championship_rules`.
    """

    #: Whether the rule can be scoped to a competitor's best N stages.
    supports_best_n: bool = True
    #: Whether a stage coefficient weights this rule's value. True for
    #: value-type rules (points and tie-break values); False for ordinal or
    #: count rules (a finishing position or a count of wins is not weighted).
    uses_coefficient: bool = False
    #: Path to this rule's own configuration form fragment, shown in the rule
    #: modal (``None`` when the rule has no options of its own). The generic
    #: ``best_n`` and ``coefficient`` fields are added by the modal from
    #: ``supports_best_n`` / ``uses_coefficient``.
    config_template: str | None = None

    best_n: int | None = None

    @staticmethod
    @abstractmethod
    def static_id() -> str:
        """Stable identifier persisted in the database and posted by the UI."""

    @staticmethod
    @abstractmethod
    def base_acronym() -> str:
        """Short column label for the results table (headers get wide fast)."""

    @staticmethod
    @abstractmethod
    def label() -> str:
        """Translated human-readable name."""

    @staticmethod
    @abstractmethod
    def description() -> str:
        """Translated one-line explanation for the rule picker."""

    @classmethod
    def from_options(cls, best_n: int | None, options: dict) -> 'ChampionshipRule':
        """Build a rule from its persisted ``best_n`` and ``options`` payload.
        The default reads only the coefficient toggle; rules with extra
        parameters override it."""
        return cls(best_n, use_coefficient=options.get('use_coefficient', True))

    def __init__(self, best_n: int | None = None, use_coefficient: bool = True):
        self.best_n = best_n if self.supports_best_n else None
        # Whether the source coefficient weights this rule's value. Only
        # meaningful for value-type rules; forced off for the rest.
        self.use_coefficient = use_coefficient if self.uses_coefficient else False

    def coefficient_for(self, participation) -> float:
        """The multiplier the source coefficient applies to this rule's value:
        the stage coefficient when enabled, otherwise 1 (unweighted)."""
        return participation.coefficient if self.use_coefficient else 1.0

    @property
    def acronym(self) -> str:
        """Column label, e.g. ``Pts`` or ``Pts4`` when scoped to the best 4."""
        base = self.base_acronym()
        return f'{base}{self.best_n}' if self.best_n else base

    @property
    def stage_metric(self) -> str:
        """Identity of this rule's per-stage value, ignoring the best-N scope.
        Rules that share it (e.g. ``Pts4`` and ``Pts5``) show a single column in
        the per-stage breakdown, since a stage's value does not depend on how
        many stages a rule keeps."""
        return self.base_acronym()

    @abstractmethod
    def scores(
        self, group: list['ReconciledCompetitor'], context: ScoringContext
    ) -> dict[int, float] | None:
        """Return this rule's value for each competitor in ``group``.

        ``None`` means the rule is not applicable to the group, as with a
        direct-encounter rule when none of the tied competitors met.
        """

    def stage_value(self, participation, context: ScoringContext) -> float | None:
        """This rule's per-stage value (higher = better), used to break best-N
        selection ties by the configured rule chain. ``None`` for rules with no
        meaningful per-stage value (direct encounter, manual), which are skipped
        when ordering a competitor's stages."""
        return None

    def stage_display(self, participation, context: ScoringContext) -> str | None:
        """This rule's contribution from a single stage, formatted for display
        (unlike :meth:`stage_value`, which is a selection key). ``None`` for
        rules with no per-stage contribution (direct encounter, manual), which
        get no column in the per-stage breakdown."""
        return None

    @classmethod
    def display_details(cls, options: dict) -> list[str]:
        """Human-readable summary parts for this rule's own options, shown on the
        configuration row. The generic best-N and coefficient details are added
        by the caller, so this only covers rule-specific options."""
        return []

    @classmethod
    def config_form_data(cls, options: dict) -> dict[str, str]:
        """This rule's own modal field values for an editing round-trip, keyed by
        form field name. The generic type / best-N / coefficient fields are added
        by the caller."""
        return {}

    @classmethod
    def parse_config(cls, data: dict[str, str]) -> tuple[dict, dict[str, str]]:
        """Parse this rule's own options from the posted form fields, returning
        ``(options, errors)`` with errors keyed by form field. The generic best-N
        and coefficient fields are handled by the caller. (Rules whose options
        depend on the championship — the aggregated tie-breaks — are the
        exception and are resolved by the caller.)"""
        return {}, {}

    def split(
        self, group: list['ReconciledCompetitor'], context: ScoringContext
    ) -> list[list['ReconciledCompetitor']]:
        """Order ``group`` and split it into subgroups still tied under this
        rule (best first). A rule that cannot separate anyone returns
        ``[group]`` unchanged."""
        scores = self.scores(group, context)
        if scores is None:
            return [group]
        return _split_by_value(group, lambda competitor: scores[id(competitor)])


class TotalPointsRule(ChampionshipRule):
    uses_coefficient = True

    @staticmethod
    def static_id() -> str:
        return 'TOTAL_POINTS'

    @staticmethod
    def base_acronym() -> str:
        return 'Pts'

    @staticmethod
    def label() -> str:
        return _('Total points')

    @staticmethod
    def description() -> str:
        return _('Sum of the points scored across the counted stages.')

    def scores(self, group, context):
        return {
            id(player): sum(
                participation_points(p, context.team_score_basis, self.use_coefficient)
                for p in best_participations(
                    player,
                    self.best_n,
                    context.team_score_basis,
                    context,
                )
            )
            for player in group
        }

    def stage_value(self, participation, context):
        return participation_points(
            participation, context.team_score_basis, self.use_coefficient
        )

    def stage_display(self, participation, context):
        return f'{self.stage_value(participation, context):g}'


class ScaledPointsRule(ChampionshipRule):
    uses_coefficient = True

    @staticmethod
    def static_id() -> str:
        return 'SCALED_POINTS'

    @staticmethod
    def base_acronym() -> str:
        return 'PS'

    @staticmethod
    def label() -> str:
        return _('Positional score')

    @staticmethod
    def description() -> str:
        return _(
            'Each stage rescaled so the winner scores 1 and the last-placed 0, '
            'then summed. Evens out stages with different field sizes.'
        )

    def scores(self, group, context):
        return {
            id(player): sum(
                scaled_stage_value(p, self.use_coefficient)
                for p in best_participations(
                    player,
                    self.best_n,
                    context.team_score_basis,
                    context,
                )
            )
            for player in group
        }

    def stage_value(self, participation, context):
        return scaled_stage_value(participation, self.use_coefficient)

    def stage_display(self, participation, context):
        return f'{self.stage_value(participation, context):.2f}'


#: The standard Formula 1 points table, used when no custom table is given.
DEFAULT_F1_POINTS: list[float] = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]


class F1PointsRule(ChampionshipRule):
    uses_coefficient = True
    config_template = '/admin/championship/rule_options/f1_points.html'

    def __init__(
        self,
        best_n: int | None = None,
        table: list[float] | None = None,
        use_coefficient: bool = True,
    ):
        super().__init__(best_n, use_coefficient)
        self.table = table or list(DEFAULT_F1_POINTS)

    @classmethod
    def from_options(cls, best_n, options):
        return cls(
            best_n,
            [float(value) for value in options.get('points', [])],
            options.get('use_coefficient', True),
        )

    @staticmethod
    def static_id() -> str:
        return 'F1_POINTS'

    @staticmethod
    def base_acronym() -> str:
        return 'Pos'

    @staticmethod
    def label() -> str:
        return _('Position-based points')

    @staticmethod
    def description() -> str:
        return _(
            'Fixed points per finishing position (e.g. 20 for first, 15 for '
            'second), summed. Positions beyond the table score nothing.'
        )

    def _f1(self, participation) -> float:
        index = participation.rank - 1
        base = self.table[index] if 0 <= index < len(self.table) else 0.0
        return base * self.coefficient_for(participation)

    def scores(self, group, context):
        return {
            id(player): sum(
                self._f1(p)
                for p in best_participations(
                    player,
                    self.best_n,
                    context.team_score_basis,
                    context,
                )
            )
            for player in group
        }

    def stage_value(self, participation, context):
        return self._f1(participation)

    def stage_display(self, participation, context):
        return f'{self._f1(participation):g}'

    @classmethod
    def display_details(cls, options):
        points = options.get('points') or []
        if points:
            table = ' '.join(f'{point:g}' for point in points)
            return [_('points: {table}').format(table=table)]
        return []

    @classmethod
    def config_form_data(cls, options):
        points = options.get('points') or []
        if points:
            return {'f1_points': ' '.join(f'{point:g}' for point in points)}
        return {}

    @classmethod
    def parse_config(cls, data):
        raw = (data.get('f1_points') or '').strip()
        points: list[float] = []
        # Space-separated so a comma can be used as the decimal separator.
        for piece in raw.split():
            try:
                points.append(float(piece.replace(',', '.')))
            except ValueError:
                return {}, {
                    'f1_points': _('Please enter a space-separated list of numbers.')
                }
        return {'points': points}, {}


class RankingPointsWithBonusRule(ChampionshipRule):
    """Points from finishing position, scaled to each tournament's size, plus a
    bonus that rewards the top finishers."""

    uses_coefficient = True
    config_template = '/admin/championship/rule_options/ranking_bonus.html'

    def __init__(
        self,
        best_n: int | None = None,
        winner_bonus: float = 0.0,
        bonus_share: float = 0.0,
        use_coefficient: bool = True,
    ):
        super().__init__(best_n, use_coefficient)
        # Both are percentages in [0, 100].
        self.winner_bonus = winner_bonus
        self.bonus_share = bonus_share

    @classmethod
    def from_options(cls, best_n, options):
        return cls(
            best_n,
            float(options.get('winner_bonus', 0.0) or 0.0),
            float(options.get('bonus_share', 0.0) or 0.0),
            options.get('use_coefficient', True),
        )

    @staticmethod
    def static_id() -> str:
        return 'RANKING_POINTS_BONUS'

    @staticmethod
    def base_acronym() -> str:
        return 'RPB'

    @staticmethod
    def label() -> str:
        return _('Ranking points with bonus')

    @staticmethod
    def description() -> str:
        return _(
            'Points by finishing position — the winner scores the field size, '
            'down to 1 for last. The top finishers also get a percentage of their '
            'ranking points as a bonus. Scaling with field size, it combines '
            'tournaments of very different sizes fairly.'
        )

    def _points(self, participation) -> float:
        field_size = participation.field_size
        rank = participation.rank
        if not rank or field_size <= 0:
            return 0.0
        ranking_points = field_size - rank + 1
        bonus = 0.0
        recipients = round(field_size * self.bonus_share / 100)
        if recipients > 0 and rank <= recipients and self.winner_bonus > 0:
            winner_bonus = field_size * self.winner_bonus / 100
            # Bonus points are rounded to a whole number.
            bonus = round(winner_bonus * (recipients - rank + 1) / recipients)
        return (ranking_points + bonus) * self.coefficient_for(participation)

    def scores(self, group, context):
        return {
            id(player): sum(
                self._points(p)
                for p in best_participations(
                    player,
                    self.best_n,
                    context.team_score_basis,
                    context,
                )
            )
            for player in group
        }

    def stage_value(self, participation, context):
        return self._points(participation)

    def stage_display(self, participation, context):
        return f'{self._points(participation):g}'

    @classmethod
    def display_details(cls, options):
        return [
            _('+{winner:g}% bonus for the top {share:g}% of competitors').format(
                winner=options.get('winner_bonus', 0),
                share=options.get('bonus_share', 0),
            )
        ]

    @classmethod
    def config_form_data(cls, options):
        return {
            'winner_bonus': f'{options.get("winner_bonus", 0):g}',
            'bonus_share': f'{options.get("bonus_share", 0):g}',
        }

    @classmethod
    def parse_config(cls, data):
        options: dict = {}
        errors: dict[str, str] = {}
        for field in ('winner_bonus', 'bonus_share'):
            text = (data.get(field) or '').strip()
            value = 0.0
            if text:
                try:
                    value = float(text.replace(',', '.'))
                    if not 0 <= value <= 100:
                        raise ValueError
                except ValueError:
                    errors[field] = _('Please enter a percentage between 0 and 100.')
                    continue
            options[field] = value
        return options, errors


class AveragePointsRule(ChampionshipRule):
    uses_coefficient = True

    @staticmethod
    def static_id() -> str:
        return 'AVERAGE_POINTS'

    @staticmethod
    def base_acronym() -> str:
        return 'øPts'

    @staticmethod
    def label() -> str:
        return _('Average points')

    @staticmethod
    def description() -> str:
        return _('Mean of the points scored over the counted stages.')

    def scores(self, group, context):
        result: dict[int, float] = {}
        for player in group:
            selected = best_participations(
                player,
                self.best_n,
                context.team_score_basis,
                context,
            )
            values = [
                participation_points(p, context.team_score_basis, self.use_coefficient)
                for p in selected
            ]
            result[id(player)] = fmean(values) if values else 0.0
        return result

    def stage_value(self, participation, context):
        return participation_points(
            participation, context.team_score_basis, self.use_coefficient
        )

    def stage_display(self, participation, context):
        return f'{self.stage_value(participation, context):g}'


class AverageRankRule(ChampionshipRule):
    @staticmethod
    def static_id() -> str:
        return 'AVERAGE_RANK'

    @staticmethod
    def base_acronym() -> str:
        return 'øRk'

    @staticmethod
    def label() -> str:
        return _('Average ranking')

    @staticmethod
    def description() -> str:
        return _(
            'Mean finishing position over the counted stages; lower is better. '
            'A position, so the stage coefficient is not applied.'
        )

    def scores(self, group, context):
        result: dict[int, float] = {}
        for player in group:
            selected = best_participations(
                player,
                self.best_n,
                context.team_score_basis,
                context,
            )
            ranks = [p.rank for p in selected if p.rank]
            result[id(player)] = -fmean(ranks) if ranks else 0.0
        return result

    def stage_value(self, participation, context):
        # Lower finishing position is better; unranked stages sort worst.
        return -float(participation.rank) if participation.rank else float('-inf')

    def stage_display(self, participation, context):
        return str(participation.rank) if participation.rank else '—'


class CountPlacesRule(ChampionshipRule):
    config_template = '/admin/championship/rule_options/count_places.html'

    def __init__(self, best_n: int | None = None, place: int = 1):
        super().__init__(best_n)
        self.place = place

    @classmethod
    def from_options(cls, best_n, options):
        return cls(best_n, int(options.get('place', 1)))

    @staticmethod
    def static_id() -> str:
        return 'COUNT_PLACES'

    @staticmethod
    def base_acronym() -> str:
        return 'Pl'

    @staticmethod
    def label() -> str:
        return _('Number of placings')

    @staticmethod
    def description() -> str:
        return _(
            'How many times the competitor finished in the chosen position '
            '(e.g. number of first places). A count, so not weighted.'
        )

    @property
    def acronym(self) -> str:
        base = f'{self.base_acronym()}{self.place}'
        return f'{base}/{self.best_n}' if self.best_n else base

    @property
    def stage_metric(self) -> str:
        return f'{self.base_acronym()}{self.place}'

    def scores(self, group, context):
        return {
            id(player): sum(
                1
                for p in best_participations(
                    player,
                    self.best_n,
                    context.team_score_basis,
                    context,
                )
                if p.rank == self.place
            )
            for player in group
        }

    def stage_value(self, participation, context):
        return 1.0 if participation.rank == self.place else 0.0

    def stage_display(self, participation, context):
        return '✓' if participation.rank == self.place else '—'

    @classmethod
    def display_details(cls, options):
        return [_('place {place}').format(place=options.get('place', 1))]

    @classmethod
    def config_form_data(cls, options):
        return {'place': str(options.get('place', 1))}

    @classmethod
    def parse_config(cls, data):
        text = (data.get('place') or '').strip()
        try:
            place = int(text) if text else 1
            if place < 1:
                raise ValueError
        except ValueError:
            return {}, {'place': _('Please enter a whole number of 1 or more.')}
        return {'place': place}, {}


class CountWinsRule(ChampionshipRule):
    @staticmethod
    def static_id() -> str:
        return 'COUNT_WINS'

    @staticmethod
    def base_acronym() -> str:
        return 'Wins'

    @staticmethod
    def label() -> str:
        return _('Number of wins')

    @staticmethod
    def description() -> str:
        return _(
            'Total games won across the counted stages. A count, so not '
            'weighted by the stage coefficient.'
        )

    def scores(self, group, context):
        return {
            id(player): sum(
                participation_wins(p)
                for p in best_participations(
                    player,
                    self.best_n,
                    context.team_score_basis,
                    context,
                )
            )
            for player in group
        }

    def stage_value(self, participation, context):
        return float(participation_wins(participation))

    def stage_display(self, participation, context):
        return str(participation_wins(participation))


class _SourceTieBreakRule(ChampionshipRule):
    """Base for rules that aggregate a specific source tie-break (e.g. Buchholz)
    across stages. The tie-break is chosen from those actually used in the
    source events; its value is read from what each source already computed and
    weighted by the stage coefficient. A stage that does not use the tie-break
    is skipped, so a competitor is not penalised for events that never had it."""

    uses_coefficient = True
    config_template = '/admin/championship/rule_options/tie_break.html'

    def __init__(
        self,
        best_n: int | None = None,
        tie_break_type: str = '',
        tie_break_options: dict | None = None,
        tie_break_acronym: str = '',
        use_coefficient: bool = True,
    ):
        super().__init__(best_n, use_coefficient)
        self.tie_break_type = tie_break_type
        self.tie_break_options = tie_break_options or {}
        self.tie_break_acronym = tie_break_acronym

    @classmethod
    def from_options(cls, best_n, options):
        tie_break = options.get('tie_break', {})
        return cls(
            best_n,
            tie_break.get('type', ''),
            tie_break.get('options', {}),
            tie_break.get('acronym', ''),
            options.get('use_coefficient', True),
        )

    @property
    def acronym(self) -> str:
        selected = self.tie_break_acronym or '?'
        base = f'{self.base_acronym()}{selected}'
        return f'{base}/{self.best_n}' if self.best_n else base

    @property
    def stage_metric(self) -> str:
        # A stage's tie-break value is the same however it is aggregated, so
        # sum/average of the same tie-break share one per-stage column.
        return self.tie_break_acronym or '?'

    def _values(self, competitor, context) -> list[float]:
        values: list[float] = []
        for p in best_participations(
            competitor,
            self.best_n,
            context.team_score_basis,
            context,
        ):
            value = context.tie_break_value(
                p, self.tie_break_type, self.tie_break_options
            )
            if value is not None:
                values.append(value * self.coefficient_for(p))
        return values

    def stage_value(self, participation, context):
        # A stage without the tie-break contributes 0 (neutral) so it still
        # produces a comparable per-stage value for selection ordering.
        value = context.tie_break_value(
            participation, self.tie_break_type, self.tie_break_options
        )
        return (value or 0.0) * self.coefficient_for(participation)

    def stage_display(self, participation, context):
        # A stage that never had this tie-break shows a dash, not a neutral 0.
        value = context.tie_break_value(
            participation, self.tie_break_type, self.tie_break_options
        )
        if value is None:
            return '—'
        return f'{value * self.coefficient_for(participation):g}'

    @classmethod
    def display_details(cls, options):
        acronym = (options.get('tie_break') or {}).get('acronym')
        return [
            _('tie-break: {acronym}').format(acronym=acronym)
            if acronym
            else _('no tie-break selected')
        ]

    @classmethod
    def config_form_data(cls, options):
        tie_break = options.get('tie_break') or {}
        if not tie_break:
            return {}
        data = {'tie_break_type': tie_break.get('type', '')}
        for key, value in (tie_break.get('options') or {}).items():
            # Tie-break option values round-trip as their form representation;
            # they are simple scalars (a switch, a select value, a number).
            if value is True:
                data[key] = 'on'
            elif value is False:
                data[key] = 'off'
            else:
                data[key] = str(value)
        return data


class SumTieBreakRule(_SourceTieBreakRule):
    @staticmethod
    def static_id() -> str:
        return 'SUM_TIE_BREAK'

    @staticmethod
    def base_acronym() -> str:
        return 'Σ'

    @staticmethod
    def label() -> str:
        return _('Sum of a tie-break')

    @staticmethod
    def description() -> str:
        return _(
            'Sum, across the counted stages, of a tie-break used in the source '
            'events (e.g. Buchholz). Stages without it are skipped.'
        )

    def scores(self, group, context):
        return {id(c): sum(self._values(c, context)) for c in group}


class AverageTieBreakRule(_SourceTieBreakRule):
    @staticmethod
    def static_id() -> str:
        return 'AVERAGE_TIE_BREAK'

    @staticmethod
    def base_acronym() -> str:
        return 'ø'

    @staticmethod
    def label() -> str:
        return _('Average of a tie-break')

    @staticmethod
    def description() -> str:
        return _(
            'Mean, over the stages that use it, of a tie-break from the source '
            'events (e.g. Buchholz).'
        )

    def scores(self, group, context):
        result: dict[int, float] = {}
        for competitor in group:
            values = self._values(competitor, context)
            result[id(competitor)] = fmean(values) if values else 0.0
        return result


class DirectEncounterRule(ChampionshipRule):
    """Order tied competitors by their results against each other.

    An incomplete mini-table must not treat an unplayed encounter as a loss.
    Each competitor therefore gets a minimum/maximum possible score range;
    only non-overlapping ranges separate the group. Repeated encounters with
    the same opponent are averaged, and forfeits are excluded, matching the
    application's tournament direct-encounter tie-break.

    For teams this is the *extended* direct encounter (Art. 13.3): the rule is
    applied first with the primary score (match or game points) and, for any
    set it leaves tied, reapplied with the secondary score. A subgroup that a
    score splits stays on that score for its own resolution (Art. 13.3, the
    TEC-2023 exercises endnote [6]), rather than restarting from the primary.
    """

    supports_best_n = False

    @staticmethod
    def static_id() -> str:
        return 'DIRECT_ENCOUNTER'

    @staticmethod
    def base_acronym() -> str:
        return 'DE'

    @staticmethod
    def label() -> str:
        return _('Direct encounter')

    @staticmethod
    def description() -> str:
        return _(
            'Results of the games the tied competitors played against each '
            'other. Skipped when they never met.'
        )

    def score_ranges(self, group, context, *, secondary=False):
        if len(group) < 2:
            return None
        members = set(map(id, group))
        points_by_player_and_opponent: dict[int, dict[int, list[float]]] = {
            id(player): defaultdict(list) for player in group
        }
        any_game = False
        for player in group:
            for participation in player.participations:
                for opponent_id, points in participation.encounters(
                    context.team_score_basis, secondary=secondary
                ):
                    opponent = context.competitor_for_opponent(
                        participation, opponent_id
                    )
                    if (
                        opponent is not None
                        and opponent is not player
                        and id(opponent) in members
                    ):
                        points_by_player_and_opponent[id(player)][id(opponent)].append(
                            points
                        )
                        any_game = True
        if not any_game:
            return None

        # Infer the win value from both sides of completed encounters. This is
        # 1 for individual games, 2 for the usual match-points system, and the
        # number of boards when team game points are used.
        encounter_totals = [1.0]
        for player_id, points_by_opponent in points_by_player_and_opponent.items():
            for opponent_id, points in points_by_opponent.items():
                opponent_points = points_by_player_and_opponent[opponent_id].get(
                    player_id
                )
                if opponent_points:
                    encounter_totals.append(fmean(points) + fmean(opponent_points))
        win_value = max(encounter_totals)

        ranges: dict[int, tuple[float, float]] = {}
        for player in group:
            points_by_opponent = points_by_player_and_opponent[id(player)]
            minimum = sum(fmean(points) for points in points_by_opponent.values())
            missing_opponents = len(group) - 1 - len(points_by_opponent)
            ranges[id(player)] = (
                minimum,
                minimum + win_value * missing_opponents,
            )
        return ranges

    def scores(self, group, context):
        ranges = self.score_ranges(group, context)
        if ranges is None or any(
            round(minimum, 6) != round(maximum, 6)
            for minimum, maximum in ranges.values()
        ):
            return None
        return {player_id: minimum for player_id, (minimum, _) in ranges.items()}

    def split(self, group, context):
        return self._resolve(group, context, secondary=False)

    def _resolve(self, group, context, secondary):
        ranges = self.score_ranges(group, context, secondary=secondary)
        if ranges is None:
            return self._fall_back(group, context, secondary)

        ordered = sorted(group, key=lambda competitor: ranges[id(competitor)][0])
        subgroups: list[list] = []
        current = [ordered[0]]
        current_maximum = ranges[id(ordered[0])][1]
        for competitor in ordered[1:]:
            minimum, maximum = ranges[id(competitor)]
            if round(minimum, 6) <= round(current_maximum, 6):
                current.append(competitor)
                current_maximum = max(current_maximum, maximum)
            else:
                subgroups.append(current)
                current = [competitor]
                current_maximum = maximum
        subgroups.append(current)

        if len(subgroups) == 1:
            return self._fall_back(group, context, secondary)

        refined: list[list] = []
        for subgroup in reversed(subgroups):
            refined.extend(self._resolve(subgroup, context, secondary))
        return refined

    def _fall_back(self, group, context, secondary):
        """A score that separates no one hands the set to the secondary score
        (Art. 13.3.1, teams). Individuals have only one score, so the set stays
        tied for the next rule."""
        if not secondary and self._has_secondary(group):
            return self._resolve(group, context, secondary=True)
        return [group]

    @staticmethod
    def _has_secondary(group) -> bool:
        return bool(group) and all(
            participation.has_secondary_score
            for competitor in group
            for participation in competitor.participations
        )


class ManualRule(ChampionshipRule):
    """Break the remaining ties by hand: the organiser drags tied competitors
    into the desired order in the ranking, which pins a manual position. Only
    competitors a rule could not otherwise separate are affected."""

    supports_best_n = False

    @staticmethod
    def static_id() -> str:
        return 'MANUAL'

    @staticmethod
    def base_acronym() -> str:
        return 'Man'

    @staticmethod
    def label() -> str:
        return _('Manual tie-break')

    @staticmethod
    def description() -> str:
        return _(
            'Order the still-tied competitors by hand, by dragging them in the ranking.'
        )

    def scores(self, group, context):
        return None

    def split(self, group, context):
        if not context.manual_positions:
            return [group]
        return _split_by_value(
            group, lambda competitor: context.manual_positions.get(competitor.key, 0)
        )


def championship_rules() -> list[type[ChampionshipRule]]:
    """All concrete rule classes, in picker order. Walks the whole subclass
    tree and skips abstract intermediates — mirrors the tie-break registry, so
    new rules (including subclasses of a shared base) are picked up on import."""
    result: list[type[ChampionshipRule]] = []
    seen: set[type[ChampionshipRule]] = set()
    stack: list[type[ChampionshipRule]] = list(ChampionshipRule.__subclasses__())
    while stack:
        rule_class = stack.pop(0)
        if rule_class in seen:
            continue
        seen.add(rule_class)
        stack.extend(rule_class.__subclasses__())
        if not inspect.isabstract(rule_class):
            result.append(rule_class)
    return result


def championship_rule_class(static_id: str) -> type[ChampionshipRule]:
    for rule_class in championship_rules():
        if rule_class.static_id() == static_id:
            return rule_class
    raise ValueError(f'Unknown championship rule type: {static_id}')


def build_rule(
    static_id: str, best_n: int | None, options: dict | None = None
) -> ChampionshipRule:
    return championship_rule_class(static_id).from_options(best_n, options or {})


def aggregatable_tie_break_types(sources) -> list[type['TieBreak']]:
    """The tie-break *types* a "sum/average of a tie-break" rule may aggregate.

    Because each source tournament holds the game data, we can COMPUTE any
    tie-break — the source event need not have been configured with it. So the
    list is the aggregatable types available across the sources, NOT only the
    ones configured. Plugins: a Championship has no single event, so its active
    plugins are the union of those enabled by the source events; a plugin
    tie-break therefore appears iff at least one source event enables its plugin
    (``TieBreakManager(event)`` only exposes types available to that event).
    Direct encounter / manual and other non-numeric tie-breaks are excluded."""
    from data.tie_breaks.managers import TieBreakManager

    seen: dict[str, type['TieBreak']] = {}
    for source in sources:
        event = getattr(source, 'event', None)
        if event is None:
            continue
        for tie_break_class in TieBreakManager(event).entity_types():
            if not tie_break_class.is_aggregatable:
                continue
            seen.setdefault(tie_break_class.static_id(), tie_break_class)
    return list(seen.values())


def rank_competitors(
    competitors: list['ReconciledCompetitor'],
    rules: list[ChampionshipRule],
    team_score_basis: TeamScoreBasis = TeamScoreBasis.SOURCE_PRIMARY,
    manual_positions: dict[str, int] | None = None,
) -> list[list['ReconciledCompetitor']]:
    """Rank individual players or teams, returning ordered tie groups."""
    context = ScoringContext(competitors, team_score_basis, manual_positions, rules)
    ordered: list[list['ReconciledCompetitor']] = (
        [list(competitors)] if competitors else []
    )
    for rule in rules:
        refined: list[list['ReconciledCompetitor']] = []
        for group in ordered:
            if len(group) == 1:
                refined.append(group)
            else:
                refined.extend(rule.split(group, context))
        ordered = refined
    return ordered


def rank_players(
    players: list['ReconciledPlayer'], rules: list[ChampionshipRule]
) -> list[list['ReconciledPlayer']]:
    """Backward-compatible individual-ranking entry point."""
    competitors = cast(list['ReconciledCompetitor'], players)
    return cast(list[list['ReconciledPlayer']], rank_competitors(competitors, rules))
