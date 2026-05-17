"""Tournament-wide norm calculations (1.4.3d, 1.5.6a).

These don't depend on any one applicant — they describe the tournament
itself. `Tournament.big_tournament_exemption` and `.high_level_tournament`
are thin `@cached_property` delegates to these functions, which keeps the
norm-logic surface here while preserving the per-instance caching the
searcher relies on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from utils.enum import PlayerRatingType, Result, TitleNorm
from utils.types import BigTournamentExemption, Federation

if TYPE_CHECKING:
    from data.tournament import Tournament


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
    host_fed = Federation(tournament.event.federation)
    eligible_players = []
    for p in tournament.tournament_players_by_id.values():
        if p.rating_type != PlayerRatingType.FIDE:
            continue
        if p.federation in (Federation('NON'), host_fed):
            continue
        missed_rounds = 0
        for pairing in p.pairings_by_round.values():
            if pairing.unplayed and pairing.result not in (
                Result.FORFEIT_WIN,
                Result.PAIRING_ALLOCATED_BYE,
                Result.REST_GAME,
            ):
                missed_rounds += 1
        if missed_rounds > 1:
            continue
        eligible_players.append(p)

    worst_players = float('inf')
    worst_federations = float('inf')
    worst_titled = float('inf')

    for rnd in range(1, tournament.rounds + 1):
        # "Present" interpretation: a player counts as present this round
        # if they played a real game OR received a Pairing Allocated Bye /
        # Rest Game. The spec says the per-round threshold must hold "for
        # this purpose" of eligibility, with PAB explicitly excluded from
        # what counts as "missing a round". Including PAB recipients here
        # matches that intent — the player is participating in the round's
        # mechanics, just not at a board. (Strict "must be at a board"
        # reading would make 1.4.3d harder to satisfy in any event with
        # bye-eligible bottom seeds — not what FIDE practice does.)
        present = []
        for p in eligible_players:
            round_pairing = p.pairings_by_round.get(rnd)
            if round_pairing and (
                round_pairing.played
                or round_pairing.result
                in (Result.PAIRING_ALLOCATED_BYE, Result.REST_GAME)
            ):
                present.append(p)

        # 1.4.2a: FID players are accepted as participants but do NOT count
        # as foreign players. 1.4.3d's "at least 20 FIDE rated foreign
        # players ... from at least 3 different federations, at least 10 of
        # whom hold ..." therefore excludes FID from all three counts.
        present_foreign = [p for p in present if p.federation != Federation('FID')]
        n_players = len(present_foreign)
        n_titled = sum(1 for p in present_foreign if p.title in TitleNorm.MASTER_TITLES)
        n_feds = len({p.federation for p in present_foreign})

        worst_players = min(worst_players, n_players)
        worst_federations = min(worst_federations, n_feds)
        worst_titled = min(worst_titled, n_titled)

    if worst_players is float('inf'):
        return BigTournamentExemption(0, 0, 0)
    return BigTournamentExemption(
        federations=int(worst_federations),
        foreigners=int(worst_players),
        titled_foreigners=int(worst_titled),
    )


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

    eligible_players = []
    for p in tournament.tournament_players_by_id.values():
        if p.rating_type != PlayerRatingType.FIDE:
            continue
        if p.federation == Federation('NON'):
            continue
        missed_rounds = 0
        for pairing in p.pairings_by_round.values():
            if pairing.unplayed and pairing.result not in (
                Result.FORFEIT_WIN,
                Result.PAIRING_ALLOCATED_BYE,
                Result.REST_GAME,
            ):
                missed_rounds += 1
        if missed_rounds > 1:
            continue
        eligible_players.append(p)

    for rnd in range(1, tournament.rounds + 1):
        # "Present" includes PAB/REST_GAME recipients — same interpretation
        # as compute_big_tournament_exemption (see comment there).
        present = []
        for p in eligible_players:
            round_pairing = p.pairings_by_round.get(rnd)
            if round_pairing and (
                round_pairing.played
                or round_pairing.result
                in (Result.PAIRING_ALLOCATED_BYE, Result.REST_GAME)
            ):
                present.append(p)
        top_rated = sorted((p.rating for p in present), reverse=True)[:40]
        if len(top_rated) < 40:
            return False
        if sum(top_rated) / len(top_rated) < 2000:
            return False
    return True
