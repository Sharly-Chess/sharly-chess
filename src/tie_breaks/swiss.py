from collections.abc import Iterator
from data.player import TournamentPlayer as Player
from data.tournament import Tournament
from data.pairing import Pairing
from data.util import Result, BoardColor

def wins(player: Player, _tournament: Tournament, /, *, max_round: int=1) -> int:
    """Computes the number of rounds where a participant obtains,
    with or without playing, as many points as awarded for a win
    before round *max_round*.
    See FIDE Handbook C.07.7.1"""
    return sum(
        pairing.result.point_value == Result.GAIN.point_value
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    )

def games_won(player: Player, _tournament: Tournament, /, *, max_round: int=1) -> int:
    """Computes the number of games a participant won 'over the board' before
    round *max_round*.
    See FIDE Handbook C.07.7.2"""
    return sum(
        pairing.result == Result.GAIN
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    )

def games_played_with_black(player: Player, _tournament: Tournament, /, *, max_round: int=1) -> int:
    """Computes the number of games played over the board with the
    black pieces before round *max_round*.
    See FIDE Handbook C.07.7.3"""
    return sum(
        pairing.color == BoardColor.BLACK
        and pairing.played
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    )

def games_won_with_black(player: Player, _tournament: Tournament, /, *, max_round: int=1) -> int:
    """Computes the number of games won over the board with the
    black pieces before round *max_round*.
    See FIDE Handbook C.07.7.4"""
    return sum(
        pairing.color == BoardColor.BLACK and
        pairing.result == Result.GAIN
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    )

def progressive_scores(player: Player, _tournament: Tournament, /, *, max_round: int=1, cut: int=0) -> float:
    """Computes the sum of progressive scores.
    After each round, a participant has a certain tournament score.
    This tie-break is calculated adding the score of the participant at the end of each round.
    Cutting *cut* rounds excludes the score achieved after the first
    *cut* rounds. By default, this value is 0.
    See FIDE Handbook C.07.7.5 and C.07.14.1"""
    return sum(
        player.points_after(r)
        for r in range(1+cut, max_round)
    )

def rounds_elected_to_play(player: Player, _tournament: Tournament, /, *, max_round) -> int:
    """Computes the number of rounds one elected to play, i.e.
    the rounds where a player did not lose by forfeit, nor elected to take a bye
    (ZPB, HPB, or FPB)
    See FIDE Handbook C.07.7.6"""
    return sum(
        pairing.result not in (
            Result.FORFEIT_LOSS,
            Result.DOUBLE_FORFEIT,
            Result.ZERO_POINT_BYE,
            Result.HALF_POINT_BYE,
            Result.FULL_POINT_BYE,
        )
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    )

    
def buchholz(player: Player, tournament: Tournament, /, *, max_round:int=1, cut_top: int=0, cut_btm: int=0, played: bool=False) -> float:
    """Computes the sum of the scores of each of the opponents of a participant,
    before round *max_round*.
    Setting *cut_top* will remove the *cut_top* highest contributions, and *cut_btm* the lowest contributions.
    Both values must be non-negative, and *cut_top* must be at most equal to *cut_btm*.
    When *played* is set, forfeit losses are considered games against the scheduled opponent.
    """

    if cut_top < 0 or cut_btm < 0:
        raise ValueError(f"Cut values must be non-nagative, got {cut_top=}, {cut_btm=}")
    elif cut_top > cut_btm:
        raise ValueError("Top cut must be at most bottom cut")
    pairings: Iterator[Pairing] = (
        pairing for round_index, pairing in player.pairings.items()
        if round_index < max_round
    )
    scores: list[float] = []
    for pairing in pairings:
        if pairing.unplayed:
            raise NotImplementedError('TODO: take care of player unplayed rounds')
        opponent: Player = tournament.players_by_id[pairing.opponent_id]
        opponent_rounds: tuple[Pairing] = tuple(
            p for round_index, p in opponent.pairings.items()
            if round_index < max_round
        )
        if any(p.requested_bye for p in opponent_rounds):
            raise NotImplementedError('TODO: take care of opponent requested byes')
        scores.append(opponent.points_before(max_round))
    scores = sorted(scores)
    if cut_top:
        return sum(scores[cut_btm:-cut_top])
    return sum(scores[cut_btm:])
    