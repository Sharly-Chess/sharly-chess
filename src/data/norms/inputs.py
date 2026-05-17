"""`NormInputs` — pairings-derived snapshot used by the per-norm checks."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import TYPE_CHECKING

from utils.enum import PlayerTitle, Result, TitleNorm
from utils.types import Federation

if TYPE_CHECKING:
    from data.player import TournamentPlayer


class RoundDecision(str, Enum):
    """How `collect_inputs` (or the subset search) treated one round."""

    INCLUDED = 'included'
    EXCLUDED = 'excluded'  # filtered out by an evaluator rule
    DROPPED = 'dropped'  # excluded post-hoc by the 1.4.1e/f search
    NO_OPPONENT = 'no_opponent'  # bye / unpaired / forfeit-win-not-counted


# Stable string keys → resolved to translated strings in the template.
# Kept here as constants so callers don't have to remember the spellings.
REASON_INCLUDED = 'included'
REASON_INCLUDED_AS_142C_LOSS = 'included_as_1_4_2c_loss'
REASON_RULE_142A = 'rule_1_4_2a'  # opponent in NON federation
REASON_RULE_142B = 'rule_1_4_2b'  # RR-only: unrated who lost every game
REASON_FORFEIT_WIN_EXCLUDED = 'forfeit_win_excluded'
REASON_BOARD_BYE = 'board_bye'  # PAB / half-point bye / rest game
REASON_UNPLAYED_NO_PAIRING = 'unplayed_no_pairing'
REASON_NO_OPPONENT = 'no_opponent'
REASON_DROPPED_BY_141EF = 'ignored_via_1_4_1ef'


@dataclass(frozen=True)
class RoundAuditEntry:
    """A single row of the per-round audit trail.

    Built by `collect_inputs` for every pairing in the applicant's
    schedule (paired or not). The subset search later produces a copy
    with the dropped rounds flipped to `DROPPED` / `REASON_DROPPED_BY_141EF`.
    """

    round_: int
    opponent: 'TournamentPlayer | None'
    raw_result: Result
    effective_result: Result | None
    decision: RoundDecision
    reason_key: str


@dataclass
class NormInputs:
    """Snapshot of pairings-derived inputs for the per-norm checks.

    Built once (`include_last_forfeit_as_loss=False`) for the default 1.4.1c
    interpretation. Rebuilt with `include_last_forfeit_as_loss=True` for the
    1.4.2c fallback if 1.4.1c fails. Carries `has_last_round_forfeit_against`
    so the orchestrator can decide whether a B-pass is worth doing.

    `included_rounds` runs parallel to `opponents` / `results_list` — entry
    `i` corresponds to round `included_rounds[i]`. The subset searcher uses
    this to drop specific rounds via `without_rounds()`.

    `round_audit` is parallel to the *full* pairings schedule (one entry per
    round, regardless of inclusion). Used by the IT1 to render the per-round
    audit trail; never read by the rule checks themselves.
    """

    played_games: int = 0
    federations_counter: Counter[Federation] = field(default_factory=Counter)
    titles_counter: Counter[PlayerTitle] = field(default_factory=Counter)
    opponents: list['TournamentPlayer'] = field(default_factory=list)
    results_list: list[Result] = field(default_factory=list)
    included_rounds: list[int] = field(default_factory=list)
    forfeits_or_byes: int = 0
    ignored_opponents_ids: set[int] = field(default_factory=set)
    score: float = 0.0
    has_last_round_forfeit_against: bool = False
    round_audit: list[RoundAuditEntry] = field(default_factory=list)

    def without_rounds(self, drop: frozenset[int]) -> 'NormInputs':
        """Return a copy with the specified rounds removed from the mix.

        Counters and score are recomputed from the kept entries.
        `forfeits_or_byes`, `ignored_opponents_ids` and
        `has_last_round_forfeit_against` are preserved unchanged — they
        describe properties of the FULL pairing set, not the search subset.

        `round_audit` is preserved unchanged here — the searcher applies
        the DROPPED-by-1.4.1e/f flip in a separate post-step (via
        `audit_with_dropped`) so the in-progress `inputs.round_audit`
        stays a faithful snapshot of what `collect_inputs` produced.
        """
        if not drop:
            return self
        kept_idx = [i for i, r in enumerate(self.included_rounds) if r not in drop]
        kept_opponents = [self.opponents[i] for i in kept_idx]
        kept_results = [self.results_list[i] for i in kept_idx]
        kept_rounds = [self.included_rounds[i] for i in kept_idx]

        feds: Counter[Federation] = Counter()
        titles: Counter[PlayerTitle] = Counter()
        for opponent in kept_opponents:
            feds[opponent.federation] += 1
            if opponent.title in TitleNorm.TITLE_HOLDERS:
                titles[opponent.title] += 1

        return NormInputs(
            played_games=len(kept_idx),
            federations_counter=feds,
            titles_counter=titles,
            opponents=kept_opponents,
            results_list=kept_results,
            included_rounds=kept_rounds,
            forfeits_or_byes=self.forfeits_or_byes,
            ignored_opponents_ids=self.ignored_opponents_ids,
            score=sum(r.points() for r in kept_results),
            has_last_round_forfeit_against=self.has_last_round_forfeit_against,
            round_audit=self.round_audit,
        )

    def audit_with_dropped(
        self, dropped_rounds: frozenset[int]
    ) -> list[RoundAuditEntry]:
        """Return a new audit list with the given rounds marked DROPPED.

        Used by `TitleNormSubsetSearcher` when a winning subset is found:
        the search's "ignored" rounds are flipped from INCLUDED (or
        whatever they were) to DROPPED with the 1.4.1e/f reason. Entries
        themselves stay frozen — we just produce a fresh list.
        """
        if not dropped_rounds:
            return self.round_audit
        return [
            replace(
                e,
                decision=RoundDecision.DROPPED,
                reason_key=REASON_DROPPED_BY_141EF,
                effective_result=None,
            )
            if e.round_ in dropped_rounds
            else e
            for e in self.round_audit
        ]
