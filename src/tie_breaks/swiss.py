from collections.abc import Iterator
from data.player import TournamentPlayer as Player
from data.tournament import Tournament
from data.pairing import Pairing
from data.util import Result, BoardColor


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
    _tournament: Tournament,
    /,
    *,
    max_round: int | None = None,
    adjust_fore: bool = False,
) -> float:
    """Computes the adjusted score of the player for the purposes of ther opponents' tie-breaks
    Only adjusts them in case of requested byes followed by all VUR.
    If *adjust_fore* is True, the adjusted score for Fore Buchholz is computed:
    games not already determined are considered a draw."""
    if max_round is None:
        max_round = max(player.pairings) + 1
    score = 0
    for round_index, pairing in player.pairings.items():
        if round_index > max_round:
            continue
        elif adjust_fore and round_index == max_round - 1:
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

def buchholz(
    player: Player,
    tournament: Tournament,
    /,
    *,
    max_round: int | None = None,
    cut_top: int = 0,
    cut_btm: int = 0,
    played: bool = False,
) -> float:
    """Computes the sum of the scores of each of the opponents of a participant,
    before round *max_round*.
    Setting *cut_top* will remove the *cut_top* highest contributions, and *cut_btm* the lowest contributions.
    Both values must be non-negative, and *cut_top* must be at most equal to *cut_btm*.
    When *fore_buchholz* is True, Fore Buchholz adjustment is used.
    When *played* is True, forfeit losses are considered games against the scheduled opponent.
    """
    # if player.id in (9, 11, 14) and fore_buchholz and max_round is None:
    #     breakpoint()
    if max_round is None:
        max_round = max(player.pairings) + 1
    if cut_top < 0 or cut_btm < 0:
        raise ValueError(f'Cut values must be non-nagative, got {cut_top=}, {cut_btm=}')
    elif cut_top > cut_btm:
        raise ValueError('Top cut must be at most bottom cut')
    pairings: dict[Pairing] = {
        round_index: pairing
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    }
    scores: list[float] = []
    voluntary_unplayed: list[float] = []
    for round_index, pairing in pairings.items():
        if pairing.unplayed:
            dummy_points = player.points_after(max_round)
            if pairing.voluntary_unplayed:
                # We must take those into account to ensure
                # correct computations for cut-1
                voluntary_unplayed.append(dummy_points)
            else:
                scores.append(dummy_points)
            continue
        opponent: Player = tournament.players_by_id[pairing.opponent_id]
        opponent_adjusted_score = adjusted_score(
            opponent, tournament, max_round=max_round
        )
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
    played: bool = False
) -> float:

    if max_round is None:
        max_round = max(player.pairings) + 1
    if cut_top < 0 or cut_btm < 0:
        raise ValueError(f'Cut values must be non-nagative, got {cut_top=}, {cut_btm=}')
    elif cut_top > cut_btm:
        raise ValueError('Top cut must be at most bottom cut')
    pairings: dict[Pairing] = {
        round_index: pairing
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    }
    scores: list[float] = []
    voluntary_unplayed: list[float] = []
    dummy_points = player.points_before(max_round - 1)
    last_pairing = pairings[max_round - 1]
    if last_pairing.result in (
        Result.FULL_POINT_BYE, Result.PAIRING_ALLOCATED_BYE,
        Result.HALF_POINT_BYE, Result.ZERO_POINT_BYE
    ):
        dummy_points += last_pairing.result.point_value
    else:
        dummy_points += Result.DRAW.point_value
    for pairing in pairings.values():
        if pairing.unplayed:
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