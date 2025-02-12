from collections import namedtuple
from contextlib import suppress
from typing import Literal
from data.player import TournamentPlayer as Player
from data.tournament import Tournament
from data.pairing import Pairing
from data.util import Result, BoardColor, TournamentPairing


def wins(player: Player, _tournament: Tournament, /, *, max_round: int | None = None) -> int:
    """Computes the number of rounds where a participant obtains,
    with or without playing, as many points as awarded for a win
    before round *max_round*.
    See FIDE Handbook C.07.7.1"""
    if max_round is None:
        max_round = max(player.pairings) + 1
    return sum(
        pairing.result.point_value == Result.GAIN.point_value
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    )


def games_won(player: Player, _tournament: Tournament, /, *, max_round: int | None = None) -> int:
    """Computes the number of games a participant won 'over the board' before
    round *max_round*.
    See FIDE Handbook C.07.7.2"""
    if max_round is None:
        max_round = max(player.pairings) + 1
    return sum(
        pairing.result == Result.GAIN
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    )


def games_played_with_black(
    player: Player, _tournament: Tournament, /, *, max_round: int | None = None
) -> int:
    """Computes the number of games played over the board with the
    black pieces before round *max_round*.
    See FIDE Handbook C.07.7.3"""
    if max_round is None:
        max_round = max(player.pairings) + 1
    return sum(
        pairing.color == BoardColor.BLACK and pairing.played
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    )


def games_won_with_black(
    player: Player, _tournament: Tournament, /, *, max_round: int | None = None
) -> int:
    """Computes the number of games won over the board with the
    black pieces before round *max_round*.
    See FIDE Handbook C.07.7.4"""
    if max_round is None:
        max_round = max(player.pairings) + 1
    return sum(
        pairing.color == BoardColor.BLACK and pairing.result == Result.GAIN
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    )


def progressive_scores(
    player: Player, _tournament: Tournament, /, *, max_round: int | None = None, cut: int = 0
) -> float:
    """Computes the sum of progressive scores.
    After each round, a participant has a certain tournament score.
    This tie-break is calculated adding the score of the participant at the end of each round.
    Cutting *cut* rounds excludes the score achieved after the first
    *cut* rounds. By default, this value is 0.
    See FIDE Handbook C.07.7.5 and C.07.14.1"""
    if max_round is None:
        max_round = max(player.pairings) + 1
    return sum(player.points_after(r) for r in range(1 + cut, max_round))


def rounds_elected_to_play(
    player: Player, _tournament: Tournament, /, *, max_round: int | None = None
) -> int:
    """Computes the number of rounds one elected to play, i.e.
    the rounds where a player did not lose by forfeit, nor elected to take a bye
    (ZPB, HPB, or FPB)
    See FIDE Handbook C.07.7.6"""
    if max_round is None:
        max_round = max(player.pairings) + 1
    return sum(
        pairing.result
        not in (
            Result.FORFEIT_LOSS,
            Result.DOUBLE_FORFEIT,
            Result.ZERO_POINT_BYE,
            Result.HALF_POINT_BYE,
            Result.FULL_POINT_BYE,
        )
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    )


def adjusted_score(
    player: Player,
    tournament: Tournament,
    /,
    *,
    max_round: int | None = None,
    adjust_fore: bool = False,
    papi_legacy: bool = False,
) -> float:
    """Computes the adjusted score of the player for the purposes of ther opponents' tie-breaks
    Only adjusts them in case of requested byes followed by all VUR.
    If *adjust_fore* is True, the adjusted score for Fore Buchholz is computed:
    games not already determined are considered a draw.
    When *papi_legacy* is True, all unplayed rounds are counted as draws."""
    if max_round is None:
        max_round = max(player.pairings) + 1
    if tournament.pairing == TournamentPairing.BERGER:
        return player.points_before(max_round)
    score = 0
    for round_index, pairing in player.pairings.items():
        if round_index > max_round:
            continue
        if papi_legacy and pairing.unplayed:
            score += Result.DRAW.point_value
            continue
        if adjust_fore and round_index == max_round - 1:
            if pairing.result in (
                Result.FULL_POINT_BYE,
                Result.PAIRING_ALLOCATED_BYE,
            ):
                score += pairing.result.point_value
            else:
                score += Result.DRAW.point_value
            continue
        if pairing.requested_bye:
            if all(
                p.voluntary_unplayed
                for index, p in player.pairings.items()
                if round_index < index < max_round
            ):
                score += Result.DRAW.point_value
            else:
                score += pairing.result.point_value
        else:
            score += pairing.result.point_value
    return score


def dummy_score(
    player: Player,
    pairing: Pairing,
    /,
    *,
    max_round: int = 1,
    round_index: int = 1,
    papi_legacy: bool = False,
    fore_modifier: bool = False,
    dummy_type: Literal['BH'] | Literal['SB'] = 'BH',
) -> float | tuple[float, Result]:
    """Computes the dummy score for the given pairing before *max_round*.
    If *dummy_type* is 'BH', returns the dummy score alone.
    If *dummy_type* is 'SB', returns the dummy score and the equivalent result
    for the given *pairing*.
    The given *pairing* must be an unplayed round, otherwise this will give a ValueError.
    If *papi_legacy* is True, *round_index* is used in the computation,
    and thus must be set correctly.
    *round_index* is not used if *papi_legacy* is False.
    """
    if dummy_type == 'BH':
        if not papi_legacy and not fore_modifier:
            return player.points_before(max_round) 
        if fore_modifier:
            dummy = player.points_before(max_round - 1)
            last_pairing = player.pairings[max_round - 1]
            if last_pairing.result in (
                Result.FULL_POINT_BYE, Result.PAIRING_ALLOCATED_BYE,
                Result.HALF_POINT_BYE, Result.ZERO_POINT_BYE
            ):
                dummy += last_pairing.result.point_value
            else:
                dummy += Result.DRAW.point_value
            return dummy
        dummy = player.points_before(round_index) + Result.DRAW.point_value * (max_round - round_index - 1)
        match pairing.result:
            case Result.FORFEIT_GAIN | Result.PAIRING_ALLOCATED_BYE | Result.FULL_POINT_BYE:
                return dummy + Result.LOSS.point_value
            case Result.HALF_POINT_BYE:
                return dummy + Result.DRAW.point_value
            case Result.ZERO_POINT_BYE | Result.FORFEIT_LOSS:
                return dummy + Result.GAIN.point_value
    elif dummy_type == 'SB':
        dummy = player.points_before(max_round)
        match pairing.result:
            case Result.FORFEIT_GAIN | Result.PAIRING_ALLOCATED_BYE | Result.FULL_POINT_BYE:
                return dummy, Result.GAIN
            case Result.HALF_POINT_BYE:
                return dummy, Result.DRAW
            case Result.ZERO_POINT_BYE | Result.FORFEIT_LOSS:
                return dummy, Result.LOSS
            case _:
                return pairing.result


def buchholz(
    player: Player,
    tournament: Tournament,
    /,
    *,
    max_round: int | None = None,
    cut_top: int = 0,
    cut_btm: int = 0,
    played_modifier: bool = False,
    papi_legacy: bool = False,
) -> float:
    """Computes the sum of the scores of each of the opponents of a participant,
    before round *max_round*.
    See FIDE Handbook C.07.8.1
    Setting *cut_top* will remove the *cut_top* highest contributions, and
    *cut_btm* the lowest contributions.
    When cutting the lowest contriibutions, all Voluntary Unplayed Rounds
    (requested byes and forfeit losses) are cut before any other round is cut.
    Both values must be non-negative, and *cut_top* must be at most equal to *cut_btm*.
    When *played_modifier* is True, forfeit losses and wins are considered
    played against the scheduled opponent.
    When *papi_legacy* is 
    """
    # if player.id in (9, 14) and papi_legacy and max_round is None:
    #     breakpoint()
    if max_round is None:
        max_round = max(player.pairings) + 1
    if cut_top < 0 or cut_btm < 0:
        raise ValueError(
            f'Cut values must be non-nagative, got {cut_top=}, {cut_btm=}')
    elif cut_top > cut_btm:
        raise ValueError('Top cut must be at most bottom cut')
    pairings: dict[Pairing] = {
        round_index: pairing
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    }
    if tournament.pairing == TournamentPairing.BERGER:
        return sum(
            adjusted_score(
                tournament.players_by_id[pairing.opponent_id],
                tournament,
                max_round=max_round,
                papi_legacy=papi_legacy)
            for pairing in pairings.values()
        )
    scores: list[float] = []
    voluntary_unplayed: list[float] = []
    for round_index, pairing in pairings.items():
        should_add_dummy = tournament.pairing.swiss and (
            (papi_legacy and pairing.unplayed) or
            (pairing.unplayed and not played_modifier) or
            (played_modifier and pairing.result in
                (Result.HALF_POINT_BYE, Result.ZERO_POINT_BYE,
                 Result.FULL_POINT_BYE, Result.PAIRING_ALLOCATED_BYE)
             )
        )
        if should_add_dummy:
            dummy_points = dummy_score(
                player,
                pairing,
                max_round=max_round,
                papi_legacy=papi_legacy,
                round_index=round_index,
            )
            if pairing.voluntary_unplayed and not papi_legacy:
                # We must take those into account to ensure
                # correct computations for cut-1
                voluntary_unplayed.append(dummy_points)
            else:
                scores.append(dummy_points)
            continue
        opponent: Player = tournament.players_by_id[pairing.opponent_id]
        if tournament.pairing.swiss:
            opponent_adjusted_score = adjusted_score(
                opponent, tournament, max_round=max_round,
                papi_legacy=papi_legacy
            )
        else:
            opponent_adjusted_score = opponent.points_after(max_round)
        scores.append(opponent_adjusted_score)
    voluntary_unplayed = sorted(voluntary_unplayed)
    scores = sorted(scores)
    scores = voluntary_unplayed + scores

    if cut_top:
        return sum(scores[cut_btm:-cut_top])
    return sum(scores[cut_btm:])


def fore_buchholz(
    player: Player,
    tournament: Tournament,
    /,
    *,
    max_round: int | None = None,
    cut_top: int = 0,
    cut_btm: int = 0,
    played_modifier: bool = False,
) -> float:
    """Computes the Buchholz score before round *max_round,
    as if all paired games for the final round hadended in draws.
    See FIDE Handbook C.07.8.3
    When *cut_top* is set, will remove the *cut_top* highest contributions
    to the Buchholz score.
    When *cut_btm* is set, will remove the *cut_btm* lowest contributions
    to the Buchholz score, starting with the Voluntary Unplayed Rounds
    (requested byes or forfeit losses).
    Both values mut be non-negative, and *cut_top* must be at most *cut_btm*
    When *played_modifier* is set to True, forfeit losses and wins are counted
    as wins against the scheduled opponent.
    """
    if max_round is None:
        max_round = max(player.pairings) + 1
    if cut_top < 0 or cut_btm < 0:
        raise ValueError(
            f'Cut values must be non-nagative, got {cut_top=}, {cut_btm=}')
    elif cut_top > cut_btm:
        raise ValueError('Top cut must be at most bottom cut')
    pairings: dict[Pairing] = {
        round_index: pairing
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    }
    scores: list[float] = []
    voluntary_unplayed: list[float] = []
    dummy_points = dummy_score(
        player,
        pairings[min(pairings)],
        max_round=max_round,
        fore_modifier=True,
    )
    for pairing in pairings.values():
        should_add_dummy = (
            (pairing.unplayed and not played_modifier) or
            (played_modifier and pairing.result in
                (Result.HALF_POINT_BYE, Result.ZERO_POINT_BYE,
                 Result.FULL_POINT_BYE, Result.PAIRING_ALLOCATED_BYE)
             )
        )
        if should_add_dummy:
            if pairing.voluntary_unplayed:
                # We must take those into account to ensure
                # correct computations for cut-1
                voluntary_unplayed.append(dummy_points)
            else:
                scores.append(dummy_points)
            continue
        opponent: Player = tournament.players_by_id[pairing.opponent_id]
        opponent_adjusted_score = adjusted_score(
            opponent, tournament, max_round=max_round,
            adjust_fore=True
        )
        scores.append(opponent_adjusted_score)
    voluntary_unplayed = sorted(voluntary_unplayed)
    scores = sorted(scores)
    scores = voluntary_unplayed + scores

    if cut_top:
        return sum(scores[cut_btm:-cut_top])
    return sum(scores[cut_btm:])


def sum_of_buchholz(
    player: Player,
    tournament: Tournament,
    /,
    *,
    max_round: int | None = None,
    fore_modifier: bool = False,
) -> float:
    """Computes the sum of Buchholz scores of the opponents before *max_round*
    If *max_round* is not provided, it will be set to the maximum round index
    of the player.
    If *fore_modifier* is True, will use Fore Bochholz instead of total Buchholz.
    If *papi_legacy* is True, will use the backwards compatible computation."""
    if max_round is None:
        max_round = max(player.pairings) + 1
    opponents: list[Player] = [
        tournament.players_by_id.get(pairing.opponent_id)
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    ]
    if fore_modifier:
        buchholz_function = fore_buchholz
    else:
        buchholz_function = buchholz
    return sum(
        buchholz_function(
            opponent,
            tournament,
            max_round=max_round,
        )
        for opponent in opponents
        if opponent is not None
    )
    

def average_of_buchholz(
    player: Player,
    tournament: Tournament,
    /,
    *,
    max_round: int | None = None,
    fore_modifier: bool = False,
) -> float:
    """Computes the average of the opponents Buchholz scores before *max_round*.
    See FIDE Handbook C.07.8.2.
    If *fore_modifier* is True, uses Fore Buchholz instead of total score."""
    if max_round is None:
        max_round = max(player.pairings) + 1
    opponents: list[Player] = [
        tournament.players_by_id[pairing.opponent_id]
        for round_index, pairing in player.pairings.items()
        if round_index < max_round and pairing.opponent_id is not None
        and pairing.played
    ]
    if fore_modifier:
        buchholz_function = fore_buchholz
    else:
        buchholz_function = buchholz
    return sum(
        buchholz_function(
            opponent,
            tournament,
            max_round=max_round,
        )
        for opponent in opponents
        if opponent is not None
    ) / len(opponents)

SBContribution = namedtuple('SBContribution', ['score', 'contribution'])

def sonneborn_berger(
    player: Player,
    tournament: Tournament,
    /,
    *,
    max_round: int | None = None,
    cut: int = 0,
    played_modifier: bool = False
) -> float:
    """Computes the Sonneborn-Berger score by adding, for each round,
    a value given by multiplying their score before *max_round* of the opponent by
    the points scored against them.
    See FIDE Handbook C.07.9.1.
    If *max_round* is None, the scores so far will be computed.
    If *cut* is more than zero, will cut the *cut* lowest contributions.
    If *played_modifier* is True, forfeit wins and losses will be counted
    as played games (only relevant in Swiss tornaments)."""
    if max_round is None:
        max_round = max(player.pairings) + 1
    if cut < 0:
        raise ValueError(f"cut must be non-negative, got: {cut}")
    if tournament.pairing == TournamentPairing.BERGER:
        played_modifier = True
    pairings: dict[int, Pairing] = {
        round_index: pairing
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    }
    general_contributions: list[SBContribution] = []
    voluntary_unplayed: list[SBContribution] = []
    for round_index, pairing in pairings.items():
        if pairing.unplayed and not played_modifier:
            dummy, result = dummy_score(
                player,
                pairing,
                max_round=max_round,
                round_index=round_index,
                dummy_type='SB')
            value = dummy * result.point_value
            if not pairing.voluntary_unplayed:
                general_contributions.append(SBContribution(dummy, value))                
            else:
                voluntary_unplayed.append(SBContribution(dummy, value))
        elif pairing.played or (
            pairing.unplayed and pairing.opponent_id is not None and played_modifier
        ):
            opponent: Player = tournament.players_by_id[pairing.opponent_id]
            opponent_score = adjusted_score(
                opponent,
                tournament,
                max_round=max_round
            )
            contribution = pairing.result.point_value * opponent_score
            general_contributions.append(SBContribution(opponent_score, contribution))
    voluntary_unplayed = sorted(voluntary_unplayed)
    general_contributions = sorted(general_contributions)
    for _ in range(cut):
        if not voluntary_unplayed:
            # Suppress, because both lists are empty at this point
            with suppress(IndexError):
                general_contributions.pop(0)
        elif not general_contributions:
            with suppress(IndexError):
                # Suppress, because both lists are empty
                voluntary_unplayed.pop(0)
        else:
            # At this point, we know both lists have at least an element
            vur = voluntary_unplayed[0]
            lsv = general_contributions[0]
            if vur.score <= lsv.score:
                voluntary_unplayed.pop(0)
            # Cut the lowest contribution from a VUR only if it is not lower
            # than the least significant value
            elif vur.contribution >= lsv.contribution:
                voluntary_unplayed.pop(0)
            else:
                general_contributions.pop(0)
    
    return sum(
        map(
            lambda t: t.contribution,
            voluntary_unplayed + general_contributions
        )
    )

def koya(
    player: Player,
    tournament: Tournament,
    /,
    *,
    max_round: int | None = None,
    limit: float | None = None,
) -> float:
    """Computes the Koya score for the *player*, i.e.
    the number of points achieved against all partiipants
    who have scored at 50% of the maximum possible
    score before *max_round* (if *limit* is not set).
    See FIDE Hanbook C.07.9.2.
    This is only used in Round-Robin tournaments, but is still
    defined for Swiss tournaments.
    If *max_round* is None, will compute the score for the whole
    tournament so far.
    If *limit* is set, this function will compute the points obtained
    against opponents who have at least *limit* points."""
    if max_round is None:
        max_round = max(player.pairings) + 1
    if limit is None:
        limit = 0.5 * Result.GAIN.point_value * (max_round - 1)
    pairings: dict[int, Pairing] = {
        round_index: pairing
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    }
    score = 0
    for _round_index, pairing in pairings.items():
        if pairing.opponent_id is None:
            continue
        opponent = tournament.players_by_id[pairing.opponent_id]
        opponent_score = opponent.points_before(max_round)
        if opponent_score >= limit:
            score += pairing.result.point_value
    return score