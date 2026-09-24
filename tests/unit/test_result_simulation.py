"""The statistical model the random tournament generator draws results from.

The check-list asks (C.04.A Annex 3, question 32) that generated results
"follow the probabilities given by the FIDE rating table such that, in a
random sample of, say, 1,000 RTG-generated tournaments where the same
player has the same rating in each tournament, the rating variation of
each player across all tournaments is close to zero". A player's rating
moves by the difference between the score they make and the score the
table expects of them, so results whose expected score matches the table
leave the rating where it was.

Reference: Otto Milvang, *Statistical model for chess tournament
simulations*, 2nd December 2024.
"""

import random

import pytest

from data.pairings.simulation import (
    draw_result,
    expected_score,
    game_probabilities,
)
from utils.enum import Result


@pytest.mark.unit
def test_the_three_outcomes_are_a_distribution():
    for white in range(1400, 2601, 200):
        for black in range(1400, 2601, 200):
            p = game_probabilities(white, black)
            assert p.white_win >= 0 and p.draw >= 0 and p.black_win >= 0
            assert abs(p.white_win + p.draw + p.black_win - 1.0) < 1e-9


@pytest.mark.unit
def test_the_expected_score_follows_the_rating_table():
    """Question 32. The score the model implies for a player, averaged over
    the two colours as the paper does, against the score the rating table
    gives for the same difference."""
    # The deviation grows with the strength of the field: 0.003 at a mean
    # of 1800, 0.011 at 2000, 0.035 at 2400 (worst at 2300 against 2500).
    # Asserted per mean rather than as one figure, so a change that makes
    # the middle of the range worse cannot hide behind the top of it.
    tolerances = {
        1600: 0.010,
        1700: 0.008,
        1800: 0.005,
        1900: 0.008,
        2000: 0.013,
        2100: 0.019,
        2200: 0.025,
        2300: 0.031,
        2400: 0.038,
    }
    for mean, tolerance in tolerances.items():
        worst = 0.0
        for difference in range(-600, 601, 50):
            first, second = mean + difference // 2, mean - difference // 2
            with_white = game_probabilities(first, second)
            with_black = game_probabilities(second, first)
            modelled = (
                with_white.white_win
                + with_black.black_win
                + (with_white.draw + with_black.draw) / 2
            ) / 2
            worst = max(worst, abs(expected_score(first, second) - modelled))
        assert worst < tolerance, f'mean {mean}: deviation {worst:.4f}'


@pytest.mark.unit
def test_white_holds_a_small_advantage_between_equals():
    """The paper's own observation: White scores about 54 to 56 percent."""
    for rating in range(1600, 2401, 200):
        score = game_probabilities(rating, rating).white_expected_score
        assert 0.51 < score < 0.56, f'{rating}: {score}'


@pytest.mark.unit
def test_stronger_players_draw_more_often():
    """Under a quarter of games among weak players, around half among
    masters — the range the model was fitted to reproduce."""
    draw_rates = [
        game_probabilities(rating, rating).draw for rating in (1500, 1800, 2100, 2400)
    ]
    assert draw_rates == sorted(draw_rates)
    assert draw_rates[0] < 0.25
    assert draw_rates[-1] > 0.45


@pytest.mark.unit
def test_drawn_results_follow_the_probabilities():
    """The drawing of a result, over enough games to show the distribution
    it is drawn from."""
    chance = random.Random(4711)
    white, black = 2200, 2000
    expected = game_probabilities(white, black)
    counts = {Result.WIN: 0, Result.DRAW: 0, Result.LOSS: 0}
    rounds = 20000
    for _ in range(rounds):
        counts[draw_result(white, black, chance)] += 1
    assert abs(counts[Result.WIN] / rounds - expected.white_win) < 0.015
    assert abs(counts[Result.DRAW] / rounds - expected.draw) < 0.015
    assert abs(counts[Result.LOSS] / rounds - expected.black_win) < 0.015


@pytest.mark.unit
def test_the_same_seed_draws_the_same_results():
    """Question 30 turns on the generator being reproducible when asked and
    random when not."""
    first = [draw_result(2000, 1900, random.Random(7)) for _ in range(1)]
    second = [draw_result(2000, 1900, random.Random(7)) for _ in range(1)]
    assert first == second
