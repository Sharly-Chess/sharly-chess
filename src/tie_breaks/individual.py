from bisect import bisect_right
from collections import namedtuple
from collections.abc import Iterable
from contextlib import suppress
from decimal import Decimal
from itertools import groupby
from math import floor, isclose
from typing import Literal
from data.player import TournamentPlayer as Player
from data.tournament import Tournament
from data.pairing import Pairing
from data.util import Result, BoardColor, TournamentPairing, TournamentRating


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
    elif cut_top + cut_btm >= max_round:
        return 0
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
    elif cut_top + cut_btm >= max_round:
        return 0
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
    if cut >= max_round:
        return 0
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


def round_fide(num: float):
    lowest_int = int(num)
    if num - lowest_int >= 0.5:
        return lowest_int + 1
    return lowest_int


def average_rating_opponents(
    player: Player,
    tournament: Tournament,
    /,
    *,
    max_round: int | None = None,
    cut_btm: int = 0,
    cut_top: int = 0,
) -> int:
    """Computes the average rating of opponents for *player* before round
    *max_round*. If *max_round* is None, computes the average of all opponents.
    Only opponents met over the board will be counted.
    See FIDE Handbook C.07.10.1
    WARNING: This assumes everyone has a rating; if an opponent does not have
    a rating, they will be removed from consideration.
    If *cut_btm* is set, will remove the lowest *cut_btm* ratings.
    If *cut_top* is set, will remove the highest *cut_top* ratings."""
    if max_round is None:
        max_round = max(player.pairings) + 1
    if cut_btm < 0 or cut_top < 0:
        raise ValueError(
            f'Cut values must be non-negative, got: {cut_btm=}, {cut_top=}'
        )
    if cut_top + cut_btm >= max_round:
        return 0
    pairings: list[Pairing] = [
        pairing
        for round_index, pairing in player.pairings.items()
        if round_index < max_round
    ]
    tournament_rating: TournamentRating = tournament.rating
    ratings = []
    for pairing in pairings:
        if pairing.unplayed:
            continue
        opponent = tournament.players_by_id[pairing.opponent_id]
        with suppress(KeyError):
            ratings.append(opponent.ratings[tournament_rating])
    ratings = sorted(ratings)
    if cut_top:
        ratings = ratings[cut_btm:-cut_top]
    else:
        ratings = ratings[cut_btm:]
    if not ratings:
        return 0
    average = sum(ratings) / len(ratings)
    return round_fide(average)



performance_table: list[int] = [
    0, 7, 14, 21, 29, 36, 43, 50, 57, 65, 72, 80, 87, 95, 102, 110, 117,
    125, 133, 141, 149, 158, 166, 175, 184, 193, 202, 211, 220, 230, 240,
    251, 262, 273, 284, 296, 309, 322, 336, 351, 366, 383, 401, 422,
    444, 470, 501, 538, 589, 677, 800
]

papi_performance_table: list[int] = performance_table[:-1] + [677, 677]

def performance_bonus(
    fractional_score: float,
    /, *,
    papi_legacy: bool = False,
) -> int:
    percent = 100 * fractional_score
    index = floor(abs(50 - percent))
    percent_int = floor(percent)
    if papi_legacy:
        bonus = papi_performance_table[index]
        smaller_difference = percent - percent_int
        if smaller_difference > 0:
            smaller_difference *= (
                papi_performance_table[index+1]
                - bonus
            )
            bonus += smaller_difference
    else:
        bonus = performance_table[index]
    if fractional_score < 0.5:
        bonus *= -1
    return bonus


def papi_estimation(
    players: Iterable[Player],
    points: float,
    /,
    *,
    max_round: int | None = None,
    papi_legacy: bool = False,
) -> dict[float, list[Player]]:
    """Compute the estimation for the group with *points* after *max_round*"""
    players = sorted(players, key=lambda player: player.points_before(max_round))
    players: dict[float, list[Player]] = {
        pts: list(group) for pts, group in groupby(players, lambda player: player.points_before(max_round))
    }
    point_keys = sorted(list(players.keys()))
    test_group = players[points]
    test_group_index = point_keys.index(points)
    group_ratings = [
        (rating := player.ratings.get(player.tournament_rating))
        for player in test_group
        if rating is not None
    ]
    if group_ratings:
        return sum(group_ratings) / len(group_ratings)
    max_possible_points = Result.GAIN.point_value * (max_round - 1)
    superior_ratings = []
    i = 0
    while not superior_ratings:
        i -= 1
        try:
            superior_points = point_keys[test_group_index - i]
            superior_group = players[test_group_index - i]
            ratings = [
                (rating := player.ratings.get(player.tounament_rating))
                for player in superior_group
                if rating is not None
            ]
            if ratings:
                superior_ratings = ratings
        except IndexError:
            break
    inferior_ratings = []
    i = 0
    while not inferior_ratings:
        i -= 1
        try:
            inferiror_group = players[test_group_index + i]
            inferiror_points = point_keys[test_group_index + i]
            ratings = [
                (rating := player.ratings.get(player.tounament_rating))
                for player in inferiror_group
                if rating is not None
            ]
            if ratings:
                superior_ratings = ratings
        except IndexError:
            break
    if not superior_ratings and not inferior_ratings:
        return performance_bonus(points / max_possible_points, papi_legacy=papi_legacy)
    test_group_bonus = performance_bonus(points / max_possible_points, papi_legacy=papi_legacy)
    if superior_ratings:
        superiror_group_bonus = performance_bonus(
            superior_points / max_possible_points,
            papi_legacy=papi_legacy
        )
    if inferior_ratings:
        inferior_group_bonus = performance_bonus(
            inferiror_points / max_possible_points,
            papi_legacy=papi_legacy
        )
    if not inferior_ratings:
        assert superior_ratings
        average_rating = sum(superior_ratings) / len(superior_ratings)
        bonus_difference = superiror_group_bonus - test_group_bonus
        return average_rating + bonus_difference
    if not superior_ratings:
        assert inferior_ratings
        average_rating = sum(inferior_ratings) / len(inferior_ratings)
        bonus_difference = test_group_bonus - inferior_group_bonus
        return average_rating + bonus_difference
    assert superior_ratings and inferior_ratings
    superiror_average = sum(superior_ratings) / len(superior_ratings)
    inferior_average = sum(inferior_ratings) / len(inferior_ratings)
    if papi_legacy:
        round_function = round
    else:
        round_function = round_fide
    return round_function(
        inferior_average 
        + (superiror_average - inferior_average) 
        * (test_group_bonus - inferior_group_bonus) 
        / (superiror_group_bonus - inferior_group_bonus)
    )

def tournament_performance_rating(
    player: Player,
    tournament: Tournament,
    /,
    *,
    max_round: int | None = None,
    papi_legacy: bool = False,
) -> int:
    """Computes the Tournament Performance Rating of the player before
    round *max_round*, i.e. the Average Rating of the Opponents, added
    to a number resulting from the conversion of the fractional score
    into RD (see FIDE Rating Regulations for the Cnversion Table).
    See FIDE Handbook C.07.10.2."""
    if max_round is None:
        max_round = max(player.pairings) + 1
    pairings: list[Pairing] = [
        pairing
        for round_index, pairing in player.pairings.items()
        if round_index < max_round and pairing.played
    ]
    tournament_rating: TournamentRating = tournament.rating
    ratings = []
    score = 0
    for pairing in pairings:
        opponent = tournament.players_by_id[pairing.opponent_id]
        with suppress(KeyError):
            if papi_legacy:
                rating = min(
                    player.ratings[tournament_rating] + 400,
                    max(player.ratings[tournament_rating] - 400, 
                        opponent.ratings[tournament_rating]))
            else:
                rating = opponent.ratings[tournament_rating]
            ratings.append(rating)
            score += pairing.result.point_value
    max_score = len(ratings) * Result.GAIN.point_value
    average = sum(ratings) / len(ratings)
    if not papi_legacy:
        fractional_score = round(score / max_score, 2)
    else:
        fractional_score = score / max_score
    bonus = performance_bonus(fractional_score, papi_legacy=papi_legacy)
    if papi_legacy:
        return round(average + bonus)
    return round_fide(average + bonus)


def average_performance_rating_opponents(
    player: Player,
    tournament: Tournament,
    /,
    *,
    max_round: int | None = None,
) -> float:
    """Computes the average of the tournament performance rating of the
    opponents before *max_round*, only taking played games into account.
    See FIDE Handbook C.07.10.4.
    If *max_round* is None, will compute the TRP of all the opponents so far.
    """
    if max_round is None:
        max_round = max(player.pairings) + 1
    played_games: list[Pairing] = [
        pairing
        for round_index, pairing in player.pairings.items()
        if round_index < max_round and pairing.played
    ]
    performance_ratings = []
    for pairing in played_games:
        opponent: Player = tournament.players_by_id[pairing.opponent_id]
        opponent_tpr = tournament_performance_rating(
            opponent,
            tournament,
            max_round=max_round
        )
        performance_ratings.append(opponent_tpr)
    
    average = sum(performance_ratings) / len(performance_ratings)
    return round_fide(average)


def win_chances(player_rating: int, opponent_rating: int) -> tuple[Decimal, Decimal]:
    difference = abs(player_rating - opponent_rating)
    lower_bounds: list[int] = [
        4, 11, 17, 18, 26, 33, 40, 47, 54, 62, 69, 77, 84, 92, 99,
        107, 114, 122, 130, 138, 146, 154, 163, 171, 180, 189, 198, 207,
        216, 226, 236, 246, 257, 268, 279, 291, 303, 316, 329, 345, 358,
        375, 392, 412, 433, 457, 485, 518, 560, 620, 736,
    ]
    difference_index = bisect_right(lower_bounds, difference) - 1
    high = Decimal(0.5) + Decimal('0.01') * difference_index
    low = 1 - high
    if player_rating >= opponent_rating:
        return high, low
    else:
        return low, high


def expected_score(player_rating: int, opponent_ratings: Iterable[int]) -> Decimal:
    chances = [
        win_chances(player_rating, opponent_rating)
        for opponent_rating in opponent_ratings
    ]
    computed_score = sum(
        chance[0] * Decimal(Result.GAIN.point_value) 
        + chance[1] * Decimal(Result.LOSS.point_value)
        for chance in chances
    )
    return computed_score


def perfect_tournament_performance(
    player: Player,
    tournament: Tournament,
    /,
    *,
    max_round: int | None = None,
) -> int:
    """Computes the Perfect Tournament Performance for the player, i.e.
    the lowest rating that a participant should have for their expected score
    to be greater than or equal to their tournament score before *max_round*.
    See FIDE Handbook C.07.10.3.
    This assumes that all players are rated, or at least have an estimation.
    """
    if max_round is None:
        max_round = max(player.pairings) + 1
    played_rounds: list[Pairing] = [
        pairing
        for round_index, pairing in player.pairings.items()
        if round_index < max_round and pairing.played 
    ]
    actual_score = Decimal(sum(pairing.result.point_value for pairing in played_rounds))
    if not played_rounds:
        return 0
    if actual_score == len(played_rounds) * Result.LOSS.point_value:
        return -800 + min(tournament.players_by_id[pairing.opponent_id].ratings[player.tournament_rating] for pairing in played_rounds)
    ratings: list[int] = [
        tournament.players_by_id[pairing.opponent_id].ratings[player.tournament_rating]
        for pairing in played_rounds
    ]
    first_estimation = tournament_performance_rating(player, tournament, max_round=max_round)
    first_expected_score = expected_score(first_estimation, ratings)
    if isclose(first_expected_score, actual_score, abs_tol=0.01):
        return round_fide(first_estimation)
    second_estimation = first_estimation * actual_score / first_expected_score
    second_estimation = round_fide(second_estimation)
    second_expected_score = expected_score(second_estimation, ratings)

    if first_expected_score >= second_expected_score:
        low, high = second_estimation, first_estimation
    else:
        low, high = first_estimation, second_estimation
    while not isclose(
        actual_score,
        mid_score := expected_score((mid := (low + high) / 2), ratings),
        abs_tol=0.01
    ):
        if mid_score >= actual_score:
            high = mid
        else:
            low = mid
    mid = round_fide(mid)
    while (mid_score := expected_score(mid, ratings)) >= actual_score:
        mid -= 1
    while (mid_score := expected_score(mid, ratings)) < actual_score:
        mid += 1
    return round_fide(mid)


def average_perfect_performance(
    player: Player,
    tournament: Tournament,
    /,
    *,
    max_round: int | None = None
) -> int:
    """Computes the average of the Perfect Tournament Performances
    of the opponents (only those who played) before round *max_round*.
    See FIDE Hand book C.07.10.5.
    If *max_round* is None, will compute for all the rounds so far."""
    if max_round is None:
        max_round = max(player.pairings) + 1
    pairings: list[Pairing] = [
        pairing
        for round_index, pairing in player.pairings.items()
        if round_index < max_round and pairing.played
    ]
    ptp = [
        perfect_tournament_performance(
            tournament.players_by_id[pairing.opponent_id],
            tournament,
            max_round=max_round
        )
        for pairing in pairings
    ]

    if not ptp:
        return 0
    return round_fide(sum(ptp) / len(ptp))