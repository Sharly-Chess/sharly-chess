"""The outcome of a simulated game, drawn from the ratings.

A random tournament generator is only useful if the results it invents
behave like real ones: the check-list asks (C.04.A Annex 3, question 32)
that they "follow the probabilities given by the FIDE rating table such
that, in a random sample of, say, 1,000 RTG-generated tournaments where
the same player has the same rating in each tournament, the rating
variation of each player across all tournaments is close to zero".

The rating table gives an expected *score*, which does not say how often
a game is drawn — and the draw rate varies enormously with the strength
of the players, from under a quarter among weak players to over half
among grandmasters. The model used here is therefore taken from Otto
Milvang, *Statistical model for chess tournament simulations* (2nd
December 2024), fitted to 7 674 837 FIDE-rated standard games played
between January 2016 and April 2023:

    Pw(Rw, Rb) = 1 / (1 + 10 ** ((Rb - Rw + W(Rm)) / S))
    Pb(Rw, Rb) = 1 / (1 + 10 ** ((Rw - Rb - B(Rm)) / S))
    Pd(Rw, Rb) = 1 - Pw - Pb
    Rm = (Rw + Rb) / 2
    W(Rm) = (Rm - 2000) * 0.0986 + 96
    B(Rm) = (Rm - 2000) * -0.157 - 150
    S = 370

``W`` carries White's advantage and ``B`` Black's disadvantage, both
growing with the strength of the players, and ``S`` spreads the
distribution. Note that the paper states these two formulas with the
signs of ``W`` and ``B`` reversed from the reference implementation it
prints a page later; the implementation is the one that agrees with the
paper's own observations, giving White 53.7% of the points between equal
players against the 54-56% the paper cites, where the stated formulas
would give White 64%. The code is followed here.

What the model is answerable for is the expected score, and it tracks the
rating table closely where the tournaments are: over a rating difference
of ±600 the score it implies differs from the table's by 0.003 at a mean
of 1800, 0.011 at 2000, and 0.035 at 2400, the deviation growing steadily
with the strength of the field. How that score divides between decisive
games and draws is looser at the top: for 2500 against 2300 the paper's own game
database shows 69.3% / 17.3% / 13.4% where the model gives 59.9% / 33.0%
/ 7.1%, the same expected score reached with too many draws. The paper
says as much -- "for rating higher than 2300, maybe S should have been
adjusted" -- and its published S of 370 is kept here rather than fitted
again, since the expected score is what question 32 measures.

The model is sound between 1600 and 2400, and serviceable from 1400 to
2600 (the author's own assessment; beyond that the games it was fitted to
grow sparse).
"""

import random
from dataclasses import dataclass

from utils.enum import Result

#: Fitted parameters, from the paper's reference implementation.
_WHITE_ADVANTAGE_SLOPE = 0.0986
_WHITE_ADVANTAGE_AT_2000 = 96.0
_BLACK_DISADVANTAGE_SLOPE = -0.157
_BLACK_DISADVANTAGE_AT_2000 = -150.0
_SPREAD = 370.0

#: What a player with no rating is taken to be worth. The model needs two
#: ratings, and a tournament may hold unrated players.
DEFAULT_RATING = 1800


@dataclass(frozen=True)
class GameProbabilities:
    """How often a game between two ratings ends each way."""

    white_win: float
    draw: float
    black_win: float

    @property
    def white_expected_score(self) -> float:
        return self.white_win + self.draw / 2


def game_probabilities(white_rating: int, black_rating: int) -> GameProbabilities:
    """The chance of each outcome of a game between these two ratings."""
    mean = (white_rating + black_rating) / 2
    white_advantage = (mean - 2000) * _WHITE_ADVANTAGE_SLOPE + _WHITE_ADVANTAGE_AT_2000
    black_disadvantage = (
        mean - 2000
    ) * _BLACK_DISADVANTAGE_SLOPE + _BLACK_DISADVANTAGE_AT_2000
    white_win = 1.0 / (
        1.0 + 10.0 ** ((black_rating - white_rating + white_advantage) / _SPREAD)
    )
    black_win = 1.0 / (
        1.0 + 10.0 ** ((white_rating - black_rating - black_disadvantage) / _SPREAD)
    )
    # The fit leaves the draw rate as the remainder, which stays positive
    # across the ratings a tournament holds; clamped so a rating outside
    # the range the model was fitted to cannot make it negative.
    draw = max(0.0, 1.0 - white_win - black_win)
    return GameProbabilities(white_win, draw, black_win)


def expected_score(player_rating: int, opponent_rating: int) -> float:
    """The expected score the rating system gives, against which the model
    above is measured (FIDE Rating Regulations B.02 Art. 8.1)."""
    return float(1.0 / (1.0 + 10.0 ** ((opponent_rating - player_rating) / 400.0)))


def draw_result(white_rating: int, black_rating: int, chance: random.Random) -> Result:
    """One game's result, drawn from the ratings."""
    probabilities = game_probabilities(white_rating, black_rating)
    roll = chance.random()
    if roll < probabilities.white_win:
        return Result.WIN
    if roll < probabilities.white_win + probabilities.draw:
        return Result.DRAW
    return Result.LOSS
