"""Tournament-wide norm calculations (1.4.3d, 1.5.6a).

These don't depend on any one applicant — they describe the tournament
itself. `Tournament.big_tournament_exemption` and `.high_level_tournament`
are thin `@cached_property` delegates to these functions, which keeps the
norm-logic surface here while preserving the per-instance caching the
searcher relies on.

The `_trail` variants build per-round detail for the calculation-details
view; they're not used on the hot path. Both `compute_*` functions and
their `_trail` siblings share the eligibility filter via private helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from utils.enum import PlayerRatingType, Result, TitleNorm
from utils.types import BigTournamentExemption, Federation

if TYPE_CHECKING:
    from data.player import TournamentPlayer
    from data.tournament import Tournament


@dataclass(frozen=True)
class BigTournamentRoundCounts:
    """Per-round breakdown of the 1.4.3d inputs. The detail view renders
    one row per round; the worst-case (minimum) row is the bottleneck
    that determines whether the exemption applies."""

    round_: int
    foreigners: int
    federations: int
    titled_foreigners: int


@dataclass(frozen=True)
class HighLevelRoundCounts:
    """Per-round breakdown of the 1.5.6a inputs. Each round must have at
    least 40 FIDE-rated players with a top-40 average rating ≥ 2000."""

    round_: int
    fide_rated_present: int
    top_40_average: float  # 0.0 when fewer than 40 players are present


def _is_present_at_round(player: 'TournamentPlayer', round_: int) -> bool:
    """A player counts as present this round if they played a real game
    OR received a Pairing-Allocated Bye / Rest Game. PAB is excluded from
    "missing a round" by the spec, so it's included here for consistency.
    """
    pairing = player.pairings_by_round.get(round_)
    if pairing is None:
        return False
    return pairing.played or pairing.result in (
        Result.PAIRING_ALLOCATED_BYE,
        Result.REST_GAME,
    )


def _missed_rounds(player: 'TournamentPlayer') -> int:
    """Count of rounds the player neither played nor received a PAB / RG /
    forfeit-win for. ≤ 1 keeps the player eligible for both 1.4.3d and
    1.5.6a tournament-wide checks."""
    missed = 0
    for pairing in player.pairings_by_round.values():
        if pairing.unplayed and pairing.result not in (
            Result.FORFEIT_WIN,
            Result.PAIRING_ALLOCATED_BYE,
            Result.REST_GAME,
        ):
            missed += 1
    return missed


def _eligible_for_143d(tournament: 'Tournament') -> list['TournamentPlayer']:
    """FIDE-rated, not NON-fed, not host-fed, ≤ 1 missed round."""
    host_fed = Federation(tournament.event.federation)
    return [
        p
        for p in tournament.tournament_players_by_id.values()
        if p.rating_type == PlayerRatingType.FIDE
        and p.federation not in (Federation('NON'), host_fed)
        and _missed_rounds(p) <= 1
    ]


def _eligible_for_156a(tournament: 'Tournament') -> list['TournamentPlayer']:
    """FIDE-rated, not NON-fed, ≤ 1 missed round. Host federation is NOT
    excluded (differs from 1.4.3d)."""
    return [
        p
        for p in tournament.tournament_players_by_id.values()
        if p.rating_type == PlayerRatingType.FIDE
        and p.federation != Federation('NON')
        and _missed_rounds(p) <= 1
    ]


def _round_counts_143d(
    eligible: list['TournamentPlayer'], round_: int
) -> BigTournamentRoundCounts:
    """Foreign FIDE-rated present this round, distinct non-FID feds, and
    GM/IM/WGM/WIM holders within that set. FID is filtered out here
    because 1.4.3d's "foreign" wording excludes FID."""
    present = [p for p in eligible if _is_present_at_round(p, round_)]
    present_foreign = [p for p in present if p.federation != Federation('FID')]
    return BigTournamentRoundCounts(
        round_=round_,
        foreigners=len(present_foreign),
        federations=len({p.federation for p in present_foreign}),
        titled_foreigners=sum(
            1 for p in present_foreign if p.title in TitleNorm.MASTER_TITLES
        ),
    )


def _round_counts_156a(
    eligible: list['TournamentPlayer'], round_: int
) -> HighLevelRoundCounts:
    """FIDE-rated present this round, plus the top-40 rating average. The
    average is 0.0 when fewer than 40 are present (insufficient data)."""
    present = [p for p in eligible if _is_present_at_round(p, round_)]
    top_rated = sorted((p.rating for p in present), reverse=True)[:40]
    avg = sum(top_rated) / len(top_rated) if len(top_rated) >= 40 else 0.0
    return HighLevelRoundCounts(
        round_=round_,
        fide_rated_present=len(present),
        top_40_average=avg,
    )


def compute_big_tournament_exemption(
    tournament: 'Tournament',
) -> BigTournamentExemption:
    """FIDE 1.4.3d — Swiss exemption inputs.

    Counts the worst (minimum) across every round of:
    - eligible foreign FIDE-rated players (≤1 missed round, not host fed),
    - distinct non-FID federations among those players,
    - GM/IM/WGM/WIM holders among those players (1.4.3d's narrower title
      set — FM/WFM don't count).

    The applicant-side norm check compares these to ≥20 / ≥3 / ≥10 to
    decide whether the 1.4.3d exemption from 1.4.3 (and 1.4.4) applies.
    """
    eligible = _eligible_for_143d(tournament)
    if not eligible or tournament.rounds < 1:
        return BigTournamentExemption(0, 0, 0)
    per_round = [
        _round_counts_143d(eligible, rnd) for rnd in range(1, tournament.rounds + 1)
    ]
    return BigTournamentExemption(
        federations=min(r.federations for r in per_round),
        foreigners=min(r.foreigners for r in per_round),
        titled_foreigners=min(r.titled_foreigners for r in per_round),
    )


def compute_big_tournament_exemption_trail(
    tournament: 'Tournament',
) -> list[BigTournamentRoundCounts]:
    """Per-round 1.4.3d breakdown for the calculation-details view.

    Returns one entry per round of the tournament. Used by the IT1
    detail mode to prove the exemption — the bottleneck round (whichever
    is smallest in each column) determines whether 1.4.3d applies."""
    eligible = _eligible_for_143d(tournament)
    return [
        _round_counts_143d(eligible, rnd) for rnd in range(1, tournament.rounds + 1)
    ]


def compute_high_level_tournament(tournament: 'Tournament') -> bool:
    """FIDE 1.5.6a — Swiss-only. Every round must have at least 40 FIDE-rated
    players whose average rating is at least 2000.

    Players are counted only if they missed at most one round (PAB /
    forfeit-win / rest-game don't count as missing). NON-federation
    players are excluded; host federation is NOT excluded here (this
    differs from 1.4.3d, which IS host-federation-blind).

    1.5.6a is explicitly a Swiss-tournament path (the spec text says
    "Individual Swiss tournament"); we return False for any non-Swiss
    pairing system so RR/DRR/Knockout events don't accidentally claim
    the exemption.
    """
    from data.pairings.systems import SwissPairingSystem

    if tournament.pairing_system != SwissPairingSystem():
        return False

    eligible = _eligible_for_156a(tournament)
    for rnd in range(1, tournament.rounds + 1):
        counts = _round_counts_156a(eligible, rnd)
        if counts.fide_rated_present < 40 or counts.top_40_average < 2000:
            return False
    return True


def compute_high_level_tournament_trail(
    tournament: 'Tournament',
) -> list[HighLevelRoundCounts]:
    """Per-round 1.5.6a breakdown for the calculation-details view.

    Returns one entry per round, regardless of pairing system — the
    template can decide whether to render. Non-Swiss tournaments don't
    qualify for 1.5.6a, but seeing the actual figures is still useful
    audit context."""
    eligible = _eligible_for_156a(tournament)
    return [
        _round_counts_156a(eligible, rnd) for rnd in range(1, tournament.rounds + 1)
    ]


def apply_143abc_exemption(
    results: dict,  # dict[TitleNorm, NormCheckResult]
    exemption_code: str,
    applicant_federation: 'Federation',
    event_federation: 'Federation',
) -> None:
    """Mutate `results` to apply the 1.4.3a/b/c exemption, if any.

    `exemption_code` is the arbiter's selection from the print option:
    - 'none'   → no manual exemption (1.4.3d still auto-applies elsewhere).
    - '1.4.3a' → National championship final. Exempts 1.4.3 only for
                 players whose federation == event's registering federation.
    - '1.4.3b' → National team championship. Same player filter as a.
    - '1.4.3c' → Zonal or sub-zonal. Exempts 1.4.3 for ALL players
                 regardless of federation.

    NONE of a/b/c exempt 1.4.4 — only 1.4.3d does that. The result's
    `is_met` honors this asymmetry via `is_143_exempt_via_abc`.

    Sets `result.rule_143_exemption` to 'a' / 'b' / 'c' / None as
    appropriate. The print templates render a badge from this field.
    """
    if exemption_code == 'none':
        return

    # a and b are player-scoped: only the registering federation's
    # players are exempt. c is tournament-scoped (applies to everyone).
    if exemption_code in ('1.4.3a', '1.4.3b'):
        if applicant_federation != event_federation:
            return

    code_map = {'1.4.3a': 'a', '1.4.3b': 'b', '1.4.3c': 'c'}
    code = code_map.get(exemption_code)
    if code is None:
        return  # unknown value — validate() should have caught this

    for res in results.values():
        res.rule_143_exemption = code
