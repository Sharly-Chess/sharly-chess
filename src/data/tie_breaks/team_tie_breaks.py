"""Team tie-break systems (FIDE Handbook C.07 §11-§13, March 2026).

Implements the four team systems that apply to Swiss / round-robin
team tournaments:
  - Match Points vs Game Points (MPvGP, §11)
  - Sistema Buchholz for teams (BH, §12)
  - Extended Sonneborn-Berger for teams (ESB, §13) with the four
    Own × Opponent score-type combinations: EMMSB, EMGSB, EGMSB, EGGSB

Each tie-break consumes ``TeamRecord`` instances (see
``team_records.py``); this lets us unit-test the systems against the
TEC-2023 published exercises by building records directly from the
crosstable rather than through the storage layer.

Knockout-only systems (BC, TBR, BBE) and EDE / SSSC are deferred to
the next phase.
"""

from abc import ABC, abstractmethod
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from types import UnionType
from typing import Any, SupportsFloat

from common.i18n import _
from data.pairings import PairingSystem
from data.player import TournamentPlayer
from data.tie_breaks.categories import (
    TeamScoreCategory,
    TeamOpponentRecordCategory,
    TieBreakCategory,
)
from data.tie_breaks.cutters import TieBreakCutter
from data.tie_breaks.options import (
    CutterTieBreakOption,
    TieBreakOption,
    ForeModifierTieBreakOption,
    NormalizationFactorOverrideTieBreakOption,
    PlayedModifierTieBreakOption,
    TeamScoreTieBreakOption,
)
from data.tie_breaks.team_records import (
    TeamRecord,
    adjust_opponent_total,
    dummy_opponent_score,
)
from data.tie_breaks.tie_breaks import (
    ForeBuchholzTieBreak,
    StandardBuchholzTieBreak,
    TieBreak,
)
from utils.enum import ScoreType


# ---------------------------------------------------------------------------
# ESB variant option (which score-type combination to use)
# ---------------------------------------------------------------------------


class ESBVariant(StrEnum):
    """The four ESB variants (TEC-2023 §10)."""

    EMMSB = 'EMMSB'  # Σ opponent_MP × own_MP_obtained
    EMGSB = 'EMGSB'  # Σ opponent_MP × own_GP_obtained
    EGMSB = 'EGMSB'  # Σ opponent_GP × own_MP_obtained
    EGGSB = 'EGGSB'  # Σ opponent_GP × own_GP_obtained

    @property
    def opponent_score_type(self) -> ScoreType:
        return (
            ScoreType.MATCH_POINTS
            if self in (ESBVariant.EMMSB, ESBVariant.EMGSB)
            else ScoreType.GAME_POINTS
        )

    @property
    def own_score_type(self) -> ScoreType:
        return (
            ScoreType.MATCH_POINTS
            if self in (ESBVariant.EMMSB, ESBVariant.EGMSB)
            else ScoreType.GAME_POINTS
        )


class ESBVariantTieBreakOption(TieBreakOption):
    """Selects which of the four ESB combinations is computed."""

    @staticmethod
    def static_id() -> str:
        return 'ESB_VARIANT'

    @property
    def type(self) -> type | UnionType:
        return str

    @property
    def default_value(self) -> Any:
        return ESBVariant.EMMSB.value

    @property
    def template_file_stem(self) -> str:
        return 'esb_variant'

    @property
    def is_variation(self) -> bool:
        return self.value != ESBVariant.EMMSB.value

    @property
    def variation_acronym(self) -> str:
        # Use the variant code as the trf-acronym suffix.
        return self.value

    def set_value_from_variation_acronym(self, acronym: str) -> bool:
        if acronym not in {v.value for v in ESBVariant}:
            return False
        self.value = acronym
        return True

    @property
    def variant(self) -> ESBVariant:
        return ESBVariant(self.value)

    @property
    def variation_name(self) -> str:
        return self.variant.value

    @property
    def variant_options(self) -> 'dict[str, Any]':
        """Select-input dict consumed by the ``esb_variant.html`` option
        template: ESBVariant.value → SelectOption(label, tooltip)."""
        from web.utils import SelectOption

        labels = {
            ESBVariant.EMMSB: _('Opponent match points × match points obtained'),
            ESBVariant.EMGSB: _('Opponent match points × game points obtained'),
            ESBVariant.EGMSB: _('Opponent game points × match points obtained'),
            ESBVariant.EGGSB: _('Opponent game points × game points obtained'),
        }
        return {
            variant.value: SelectOption(
                name=f'{variant.value} — {labels[variant]}',
                tooltip=labels[variant],
            )
            for variant in ESBVariant
        }


# ---------------------------------------------------------------------------
# Cut-1 only for ESB (no median)
# ---------------------------------------------------------------------------


class ESBCutterTieBreakOption(CutterTieBreakOption):
    """ESB-specific cutter: Cut-1 / Cut-2 allowed, no Median (the rules
    explicitly exclude Median modifiers for ESB-type tie-breaks because
    Median would discard the heaviest opponents, contradicting the
    tie-break's design — TEC §10)."""

    @staticmethod
    def static_id() -> str:
        return 'ESB_CUTTER'


# ---------------------------------------------------------------------------
# TeamTieBreak base class
# ---------------------------------------------------------------------------


class TeamTieBreak(TieBreak, ABC):
    """Team-level tie-breaks (FIDE Handbook C.07 §11-§13).

    Concrete subclass of :class:`TieBreak` so storage, configuration
    and plugin discovery are unified. The individual-side
    :meth:`compute_player_value` is stubbed to zero — team tie-breaks
    are dispatched through :meth:`compute_team_value` /
    :meth:`compute_all_team_values`, and callers that expect a numeric
    per-player value should filter by :attr:`is_team_tiebreak` first.
    """

    @property
    def is_team_tiebreak(self) -> bool:
        return True

    @property
    def supports_team_mode(self) -> bool:
        return True

    @property
    def is_used_for_team_ranking(self) -> bool:
        """Team-score tie-breaks are not "applied per player and
        summed" the way Buchholz can be — they own the team ranking
        directly. So they don't participate in the legacy per-player
        team-ranking aggregation path."""
        return False

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> SupportsFloat:
        return 0.0

    @abstractmethod
    def compute_team_value(
        self,
        team_record: TeamRecord,
        all_records: dict[int, TeamRecord],
        tournament_context: 'TeamTieBreakContext',
        *,
        after_round: int,
    ) -> SupportsFloat:
        """Compute the tie-break value for one team. ``all_records`` is
        keyed by team_id and contains every team that participated."""

    @property
    def is_computed_per_team(self) -> bool:
        """True if the tie-break is a scalar function of a single team.
        False for group-level tie-breaks (e.g. EDE) which inspect every
        tied team at once to produce a relative ranking."""
        return True

    def compute_all_team_values(
        self,
        tied_groups: list[list[TeamRecord]],
        all_records: dict[int, TeamRecord],
        tournament_context: 'TeamTieBreakContext',
        *,
        after_round: int,
    ) -> dict[int, float]:
        """Compute values for every tied team. Default implementation
        delegates to :meth:`compute_team_value` per team; group-level
        tie-breaks (EDE) override this to perform relative ranking."""
        result: dict[int, float] = {}
        for group in tied_groups:
            for team in group:
                value = self.compute_team_value(
                    team,
                    all_records,
                    tournament_context,
                    after_round=after_round,
                )
                result[team.team_id] = float(value)
        return result


# ---------------------------------------------------------------------------
# Tournament context (primary/secondary score type + match-point scale)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TeamTieBreakContext:
    """Tournament-level constants the tie-breaks need.

    Decoupling these from ``Tournament`` keeps the tie-breaks unit-
    testable: a test can build a context directly and feed records
    that mirror a published exercise without spinning up a database."""

    primary_score: ScoreType
    secondary_score: ScoreType
    rounds: int
    win_mp: float
    draw_mp: float
    loss_mp: float
    # Number of players fielded per team per match — sets the upper
    # bound on game points per match (1 GP per board with 1-½-0).
    team_player_count: int
    # The GP awarded to a team for a half-match draw against a virtual
    # opponent (Art. 16.3.2 dummy opponent). For 4-player teams under
    # standard 2-1-0 / 1-½-0 scoring, this is 4 × ½ = 2 GP.
    draw_gp: float

    @property
    def max_score_per_match(self) -> dict[ScoreType, float]:
        return {
            ScoreType.MATCH_POINTS: self.win_mp,
            ScoreType.GAME_POINTS: float(self.team_player_count),
        }

    @property
    def min_score_per_match(self) -> dict[ScoreType, float]:
        return {
            ScoreType.MATCH_POINTS: self.loss_mp,
            ScoreType.GAME_POINTS: 0.0,
        }


# ---------------------------------------------------------------------------
# Adjusted-score helpers (Art. 16 dummy-opponent + ZPB-not-followed-by-play)
# ---------------------------------------------------------------------------


def _adjust_opponent_total(
    opponent: TeamRecord,
    score_type: ScoreType,
    context: TeamTieBreakContext,
    *,
    after_round: int,
) -> float:
    return adjust_opponent_total(
        opponent,
        score_type,
        after_round=after_round,
        draw_mp=context.draw_mp,
        draw_gp=context.draw_gp,
    )


def _dummy_opponent_score(
    own_record: TeamRecord,
    score_type: ScoreType,
    context: TeamTieBreakContext,
    *,
    after_round: int,
) -> float:
    return dummy_opponent_score(
        own_record,
        score_type,
        after_round=after_round,
        rounds=context.rounds,
        win_mp=context.win_mp,
    )


# ---------------------------------------------------------------------------
# MPvGP
# ---------------------------------------------------------------------------


class MatchPointsVsGamePointsTieBreak(TeamTieBreak):
    """The secondary score (the one not used as primary). C.07.§11."""

    @staticmethod
    def static_id() -> str:
        return 'TEAM_MPVGP'

    @staticmethod
    def static_name() -> str:
        return _('Match points vs game points')

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return []

    @property
    def base_acronym(self) -> str:
        return 'MPvGP'

    @property
    def base_help_text(self) -> str:
        return _(
            'The team score that is not used as the primary score '
            '(match points if the primary is game points and vice versa).'
        )

    @property
    def category(self) -> TieBreakCategory:
        return TeamScoreCategory()

    def is_compatible_with(self, pairing_system: PairingSystem) -> bool:
        # "The score that is not used as primary" needs the system to
        # expose both score types; on systems with only game points
        # there's nothing to return.
        if not pairing_system.supports_match_points:
            return False
        return super().is_compatible_with(pairing_system)

    def compute_team_value(
        self,
        team_record: TeamRecord,
        all_records: dict[int, TeamRecord],
        tournament_context: TeamTieBreakContext,
        *,
        after_round: int,
    ) -> float:
        return team_record.total(tournament_context.secondary_score)


# ---------------------------------------------------------------------------
# Extended Sonneborn-Berger for teams (4 variants)
# ---------------------------------------------------------------------------


class ExtendedSonnebornBergerTeamTieBreak(TeamTieBreak):
    """ESB for teams. For each round, multiply the opponent's total
    (per ``ESBVariant.opponent_score_type``) by the team's own score
    in that match (per ``ESBVariant.own_score_type``). Sum, with
    optional Cut-1 / Cut-2.

    Forfeit losses and ZPB contribute zero by construction (own_score
    is zero); HPB contributes a non-zero amount (own_score equals draw
    points) — that contribution is treated as VUR for the cut rule.
    """

    @staticmethod
    def static_id() -> str:
        return 'TEAM_EXTENDED_SB'

    @staticmethod
    def static_name() -> str:
        return _('Extended Sonneborn-Berger')

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [ESBVariantTieBreakOption, ESBCutterTieBreakOption]

    @cached_property
    def variant(self) -> ESBVariant:
        return self._get_option(ESBVariantTieBreakOption).variant

    @cached_property
    def cutter(self) -> TieBreakCutter:
        return self._get_option(ESBCutterTieBreakOption).cutter

    def is_compatible_with(self, pairing_system: PairingSystem) -> bool:
        # Variants whose enum names a match-point side need the
        # pairing system to expose match points.
        uses_mp = ScoreType.MATCH_POINTS in (
            self.variant.opponent_score_type,
            self.variant.own_score_type,
        )
        if uses_mp and not pairing_system.supports_match_points:
            return False
        return super().is_compatible_with(pairing_system)

    @property
    def base_acronym(self) -> str:
        return self.variant.value

    @property
    def acronym(self) -> str:
        # The variant option is already encoded in ``base_acronym``
        # (e.g. ``EMGSB``) — don't repeat it. Append only the cutter.
        parts: list[str] = [self.base_acronym]
        cutter_option = self._get_option(ESBCutterTieBreakOption)
        if cutter_option.is_variation and cutter_option.variation_acronym:
            parts.append(cutter_option.variation_acronym)
        return '/'.join(parts)

    @property
    def picker_acronym(self) -> str:
        # The four FIDE variants (EMMSB/EMGSB/EGMSB/EGGSB) are all
        # ESB — the variant is a configurable option, so the picker
        # names the family.
        return 'ESB'

    @property
    def picker_help_text(self) -> str:
        # ``base_help_text`` describes the configured variant — for
        # the family picker we want a variant-agnostic summary.
        return _(
            'For each round, sum the opponent score multiplied by the '
            'team score obtained in that match across all rounds. '
            'The four variants (EMMSB / EMGSB / EGMSB / EGGSB) choose '
            'which score type — match points or game points — is used '
            'on each side; pick one in the variant option below '
            '(FIDE Handbook C.07 §13).'
        )

    @property
    def base_help_text(self) -> str:
        return _(
            'For each round, the opponent total {opp} multiplied by '
            'the team {own} obtained in that match, summed across all '
            'rounds (FIDE Handbook C.07 §13).'
        ).format(
            opp=_(self.variant.opponent_score_type.value),
            own=_(self.variant.own_score_type.value),
        )

    @property
    def category(self) -> TieBreakCategory:
        return TeamOpponentRecordCategory()

    def compute_team_value(
        self,
        team_record: TeamRecord,
        all_records: dict[int, TeamRecord],
        tournament_context: TeamTieBreakContext,
        *,
        after_round: int,
    ) -> float:
        opp_score_type = self.variant.opponent_score_type
        own_score_type = self.variant.own_score_type
        cut = self.cutter.bottom_cut
        if cut >= after_round:
            return 0.0

        @dataclass(frozen=True, order=True)
        class _Contribution:
            opp_total: float
            value: float

        general: list[_Contribution] = []
        vur: list[_Contribution] = []
        for match in team_record.matches:
            if match.round_ > after_round:
                continue
            if match.unplayed:
                opp_total = _dummy_opponent_score(
                    team_record,
                    opp_score_type,
                    tournament_context,
                    after_round=after_round,
                )
            else:
                assert match.opponent_id is not None
                opponent = all_records[match.opponent_id]
                opp_total = _adjust_opponent_total(
                    opponent,
                    opp_score_type,
                    tournament_context,
                    after_round=after_round,
                )
            own = team_record.own_against(match, own_score_type)
            contribution = _Contribution(opp_total=opp_total, value=opp_total * own)
            if match.voluntary_unplayed:
                vur.append(contribution)
            else:
                general.append(contribution)

        vur.sort()
        general.sort()
        # VUR cut rule (matches the individual SB implementation):
        # the natural least-significant value is the contribution with
        # the lowest opp_total (tie-break: lowest contribution). A VUR
        # contribution is dropped first only when (a) its opp_total is
        # already at or below the general LSV opp_total — natural cut —
        # or (b) its contribution value is at least the general LSV
        # contribution, in which case Art. 16.5 forces the cut to deny
        # the competitor any benefit from the voluntary absence.
        for _step in range(cut):
            if not vur:
                with suppress(IndexError):
                    general.pop(0)
            elif not general:
                with suppress(IndexError):
                    vur.pop(0)
            else:
                v = vur[0]
                g = general[0]
                if v.opp_total <= g.opp_total:
                    vur.pop(0)
                elif v.value >= g.value:
                    vur.pop(0)
                else:
                    general.pop(0)
        return sum(c.value for c in vur) + sum(c.value for c in general)


# ---------------------------------------------------------------------------
# Scores and Schedule Strength Combination (SSSC, C.07 §13)
# ---------------------------------------------------------------------------


class ScoresAndScheduleStrengthCombinationTieBreak(TeamTieBreak):
    """secondary_score + (Buchholz on the primary) / normalisation_factor.

    The normalisation factor F_N rescales the Buchholz term so it lives
    on the same order of magnitude as the secondary score, preserving
    the intent that schedule strength should refine, not overwhelm,
    the raw scores. It equals floor(max_primary_total / max_secondary_per_round).
    """

    @staticmethod
    def static_id() -> str:
        return 'TEAM_SSSC'

    @staticmethod
    def static_name() -> str:
        return _('Scores + Schedule Strength (SSSC)')

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [
            PlayedModifierTieBreakOption,
            ForeModifierTieBreakOption,
            NormalizationFactorOverrideTieBreakOption,
        ]

    @property
    def base_acronym(self) -> str:
        return 'SSSC'

    @property
    def base_help_text(self) -> str:
        return _(
            'Secondary score plus the team Buchholz on the primary '
            'score divided by a normalisation factor (FIDE Handbook '
            'C.07 §13).'
        )

    @property
    def category(self) -> TieBreakCategory:
        return TeamOpponentRecordCategory()

    @staticmethod
    def normalization_factor(context: TeamTieBreakContext) -> int:
        max_primary_round = context.max_score_per_match[context.primary_score]
        max_secondary_round = context.max_score_per_match[context.secondary_score]
        max_primary_total = context.rounds * max_primary_round
        if max_secondary_round <= 0:
            return 1
        return int(max_primary_total // max_secondary_round)

    def compute_team_value(
        self,
        team_record: TeamRecord,
        all_records: dict[int, TeamRecord],
        tournament_context: TeamTieBreakContext,
        *,
        after_round: int,
    ) -> float:
        secondary = team_record.total(tournament_context.secondary_score)
        team_score_value = (
            TeamScoreTieBreakOption.VALUE_GP
            if tournament_context.primary_score == ScoreType.GAME_POINTS
            else TeamScoreTieBreakOption.VALUE_MP
        )
        sub_options: list[TieBreakOption] = [TeamScoreTieBreakOption(team_score_value)]
        try:
            played = self._get_option(PlayedModifierTieBreakOption)
            if played.value:
                sub_options.append(played)
        except KeyError:
            pass
        fore = False
        try:
            fore_opt = self._get_option(ForeModifierTieBreakOption)
            fore = bool(fore_opt.value)
        except KeyError:
            pass
        bh_cls: type[TieBreak] = (
            ForeBuchholzTieBreak if fore else StandardBuchholzTieBreak
        )
        bh = float(
            bh_cls(sub_options).compute_team_value(
                team_record,
                all_records,
                tournament_context,
                after_round=after_round,
            )
        )
        # /Kx override: use the explicit factor when set, else compute.
        override = 0
        try:
            override = int(
                self._get_option(NormalizationFactorOverrideTieBreakOption).value
            )
        except KeyError:
            pass
        factor = override if override else self.normalization_factor(tournament_context)
        return secondary + bh / factor


# ---------------------------------------------------------------------------
# Extended Direct Encounter (EDE, C.07 §11)
# ---------------------------------------------------------------------------


class ExtendedDirectEncounterTieBreak(TeamTieBreak):
    """Direct-encounter ranking with primary→secondary fallback and
    recursive subgroup resolution.

    Process (TEC §11):
      1. Build a separate crosstable using only matches between the
         tied teams (in Swiss, only played matches; forfeits ignored).
      2. Compute each team's sub-score using the primary score type.
      3. Split into subgroups using min/max possible sub-scores (when
         a sub-match wasn't played, min = loss value, max = win value
         per the score type).
      4. If no split is possible, retry the whole step with the
         secondary score. Still no split → leave the group tied.
      5. Recurse into every subgroup of size ≥ 2 with the score type
         that produced the split (TEC endnote [6]: a single application
         of the tie-break stays on whichever score finally succeeded).

    The result for each team is a within-group rank delta (0 = worst
    of the group, larger = better), so the surrounding standings
    machinery can break the parent tie by sorting on the delta.
    """

    @staticmethod
    def static_id() -> str:
        return 'TEAM_EDE'

    @staticmethod
    def static_name() -> str:
        return _('Extended Direct Encounter')

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [PlayedModifierTieBreakOption]

    @property
    def base_acronym(self) -> str:
        return 'EDE'

    @property
    def base_help_text(self) -> str:
        return _(
            'Direct-encounter ranking for tied teams using a separate '
            'crosstable, with secondary-score fallback and recursive '
            'sub-group resolution.'
        )

    @property
    def category(self) -> TieBreakCategory:
        return TeamOpponentRecordCategory()

    @property
    def is_computed_per_team(self) -> bool:
        return False

    @property
    def display_rank_delta(self) -> bool:
        return True

    @property
    def allow_multiple(self) -> bool:
        return True

    def compute_team_value(
        self,
        team_record: TeamRecord,
        all_records: dict[int, TeamRecord],
        tournament_context: TeamTieBreakContext,
        *,
        after_round: int,
    ) -> float:
        return 0.0

    def compute_all_team_values(
        self,
        tied_groups: list[list[TeamRecord]],
        all_records: dict[int, TeamRecord],
        tournament_context: TeamTieBreakContext,
        *,
        after_round: int,
    ) -> dict[int, float]:
        values: dict[int, float] = {}
        for group in tied_groups:
            self._resolve(
                group,
                0,
                values,
                tournament_context,
                after_round,
                tournament_context.primary_score,
            )
        return values

    def _resolve(
        self,
        group: list[TeamRecord],
        min_value: int,
        values: dict[int, float],
        context: TeamTieBreakContext,
        after_round: int,
        score_type: ScoreType,
    ) -> None:
        if len(group) == 1:
            values[group[0].team_id] = float(min_value)
            return
        min_max = {
            t.team_id: self._team_min_max(t, group, score_type, context, after_round)
            for t in group
        }
        subgroups = self._split(min_max, group)
        if len(subgroups) > 1:
            for sub in subgroups:
                self._resolve(sub, min_value, values, context, after_round, score_type)
                min_value += len(sub)
            return
        # Split failed — fall back to secondary if we were on primary,
        # otherwise leave the entire group tied at the current rank.
        if score_type == context.primary_score:
            self._resolve(
                group,
                min_value,
                values,
                context,
                after_round,
                context.secondary_score,
            )
            return
        for team in group:
            values[team.team_id] = float(min_value)

    def _team_min_max(
        self,
        team: TeamRecord,
        group: list[TeamRecord],
        score_type: ScoreType,
        context: TeamTieBreakContext,
        after_round: int,
    ) -> tuple[float, float]:
        """Return (min, max) of the score this team can have in the
        sub-crosstable restricted to ``group`` opponents, averaging
        repeated meets and treating missing matches as worst/best
        case under the active score type.

        ``/P`` (PlayedModifier) flag includes forfeit wins/losses in
        the sub-crosstable as if they were played (Swiss default
        ignores them — TEC §11)."""
        try:
            played_modifier = bool(self._get_option(PlayedModifierTieBreakOption).value)
        except KeyError:
            played_modifier = False
        group_ids = {t.team_id for t in group if t.team_id != team.team_id}
        played_score_by_opp: dict[int, list[float]] = {}
        for match in team.matches:
            if match.round_ > after_round:
                continue
            counts = match.played or (played_modifier and match.opponent_id is not None)
            if not counts or match.opponent_id is None:
                continue
            if match.opponent_id in group_ids:
                played_score_by_opp.setdefault(match.opponent_id, []).append(
                    team.own_against(match, score_type)
                )
        accrued = 0.0
        unplayed_count = 0
        for opp_id in group_ids:
            scores = played_score_by_opp.get(opp_id)
            if scores:
                accrued += sum(scores) / len(scores)
            else:
                unplayed_count += 1
        max_per = context.max_score_per_match[score_type]
        min_per = context.min_score_per_match[score_type]
        return (
            accrued + min_per * unplayed_count,
            accrued + max_per * unplayed_count,
        )

    @staticmethod
    def _split(
        min_max_by_id: dict[int, tuple[float, float]],
        group: list[TeamRecord],
    ) -> list[list[TeamRecord]]:
        team_by_id = {t.team_id: t for t in group}
        sorted_items = sorted(min_max_by_id.items(), key=lambda kv: kv[1])
        if not sorted_items:
            return []
        first_id, (first_min, first_max) = sorted_items[0]
        cur_max = first_max
        current: list[TeamRecord] = [team_by_id[first_id]]
        subgroups: list[list[TeamRecord]] = []
        for team_id, (min_, max_) in sorted_items[1:]:
            if min_ <= cur_max:
                cur_max = max(cur_max, max_)
                current.append(team_by_id[team_id])
            else:
                subgroups.append(current)
                cur_max = max_
                current = [team_by_id[team_id]]
        subgroups.append(current)
        return subgroups
