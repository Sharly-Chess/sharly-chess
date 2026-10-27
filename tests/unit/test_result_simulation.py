"""The probabilities the random tournament generator draws results from.

The check-list asks (C.04.A Annex 3, question 32) that generated results
"follow the probabilities given by the FIDE rating table such that, in a
random sample of, say, 1,000 RTG-generated tournaments where the same
player has the same rating in each tournament, the rating variation of
each player across all tournaments is close to zero". A player's rating
moves by the difference between the score they make and the score the
table expects of them, so results whose expected score is the table's
leave the rating where it was.

The draw rate comes from Otto Milvang, *Statistical model for chess
tournament simulations*, 2nd December 2024; the expected score comes from
the rating table (B.02 Art. 8.1).
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
def test_the_expected_score_is_the_rating_table_s():
    """Question 32. The decisive games are divided so that the expected
    score is the table's, for either colour and at any difference, which
    leaves nothing for a sample to accumulate."""
    for mean in range(1400, 2601, 100):
        for difference in range(-600, 601, 50):
            first, second = mean + difference // 2, mean - difference // 2
            probabilities = game_probabilities(first, second)
            assert (
                abs(probabilities.white_expected_score - expected_score(first, second))
                < 1e-9
            ), f'{first} against {second}'


@pytest.mark.unit
def test_neither_colour_is_favoured():
    """Between equal ratings the table expects half a point of each side,
    and the results are drawn to give it: a colour advantage is a point the
    rating system does not expect, and it cancels only for a player whose
    colours balance."""
    for rating in range(1400, 2601, 100):
        probabilities = game_probabilities(rating, rating)
        assert abs(probabilities.white_expected_score - 0.5) < 1e-9
        assert abs(probabilities.white_win - probabilities.black_win) < 1e-9


@pytest.mark.unit
def test_a_gulf_in_rating_leaves_the_weaker_side_nothing_but_draws():
    """Far enough apart, the table expects the weaker side less than half
    the games the draw rate would give them. The draws give way rather than
    the expected score, which the table settles."""
    probabilities = game_probabilities(2200, 2600)
    assert probabilities.white_win == 0.0
    assert probabilities.draw == pytest.approx(2 * expected_score(2200, 2600))
    assert probabilities.white_expected_score == pytest.approx(
        expected_score(2200, 2600)
    )


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
