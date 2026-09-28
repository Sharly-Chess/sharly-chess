"""Measure the rating a generated tournament hands out.

The check-list asks (C.04.A Annex 3, question 32) whether the results the
generator produces "follow the probabilities given by the FIDE rating
table such that, in a random sample of, say, 1,000 RTG-generated
tournaments where the same player has the same rating in each tournament,
the rating variation of each player across all tournaments is close to
zero".

A player's rating moves by K times the difference between the score they
made and the score the rating table expected of them against the
opponents they met. Run the same field through many tournaments and that
difference should cancel: a generator whose results are drawn from the
stated ratings gives nobody rating, while one drawing from a hidden
playing strength pays the strong steadily and takes from the weak.

Every player keeps the same rating in every tournament, so the figure is
the generator's and not an artefact of the field changing.

    PYTHONPATH=src:. ./venv/bin/python scripts/fide/rating_variation.py 1000
"""

import sys
from collections import defaultdict
from math import sqrt
from pathlib import Path

from common import TMP_DIR
from common.logger import print_interactive_error, print_interactive_info
from data.pairings.simulation import expected_score

#: How much one game's score wanders from its expectation, as a standard
#: deviation: a score of nothing, a half or one against an expectation
#: between them. Used to tell a drift that is chance from one that is not.
GAME_DEVIATION = 0.42

#: The development coefficient rating changes are multiplied by. Only used
#: to put the figure in rating points; the difference it multiplies is what
#: question 32 is about.
K_FACTOR = 20

#: The result letters of a game played over the board, and what the player
#: on that side scored. Everything else -- byes, forfeits, absences -- has
#: no opponent rating to expect a score against, so it is left out.
PLAYED_RESULTS = {'1': 1.0, '=': 0.5, '0': 0.0, 'W': 1.0, 'D': 0.5, 'L': 0.0}


def measure(trf_path: Path) -> dict[int, tuple[float, int]]:
    """Per player, the points made less the points the table expected, and
    the number of games it was made over."""
    from data.input_output.trf.trf_serializer import TrfSerializer

    with open(trf_path, encoding='ascii') as file:
        tournament = TrfSerializer.load(file)
    rating_of = {player.id: player.rating for player in tournament.players}
    variation: dict[int, tuple[float, int]] = {}
    for player in tournament.players:
        difference = 0.0
        games = 0
        for game in player.games:
            scored = PLAYED_RESULTS.get(game.result)
            if scored is None or not game.opponent_id:
                continue
            opponent_rating = rating_of.get(game.opponent_id)
            if not opponent_rating or not player.rating:
                continue
            difference += scored - expected_score(player.rating, opponent_rating)
            games += 1
        variation[player.id] = (difference, games)
    return variation


def main(count: int, players: int = 40, rounds: int = 9) -> int:
    from data.pairings.random_tournaments import (
        Frequency,
        TournamentSettings,
        generate_tournament_file,
    )

    directory: Path = TMP_DIR / 'rating_variation'
    directory.mkdir(exist_ok=True, parents=True)
    # The same rating for the same player in every tournament, which is
    # what makes the figure comparable across the sample. Nothing is left
    # unplayed: question 32 is about the game results, and a bye has no
    # opponent to expect a score against.
    ratings = [2400 - index * 10 for index in range(players)]
    settings = TournamentSettings(
        players=players,
        rounds=rounds,
        ratings=ratings,
        full_point_byes=Frequency(count=0),
        half_point_byes=Frequency(count=0),
        zero_point_byes=Frequency(count=0),
        forfeit_wins=Frequency(count=0),
        forfeit_losses=Frequency(count=0),
        unusual_results=Frequency(count=0),
    )

    totals: dict[int, float] = defaultdict(float)
    games: dict[int, int] = defaultdict(int)
    tournament_file = directory / 'tournament.trf'
    for index in range(max(count, 1)):
        generate_tournament_file(settings, tournament_file, seed=index)
        for player_id, (difference, played) in measure(tournament_file).items():
            totals[player_id] += difference
            games[player_id] += played
        if (index + 1) % 100 == 0:
            print_interactive_info(f'{index + 1} tournaments')

    print_interactive_info(
        f'Rating variation over {count} tournaments of {players} players '
        f'and {rounds} rounds'
    )
    per_game = {
        player_id: totals[player_id] / games[player_id]
        for player_id in totals
        if games[player_id]
    }
    worst_id = max(per_game, key=lambda player_id: abs(per_game[player_id]))
    print_interactive_info(f'- Games counted: {sum(games.values())}')
    print_interactive_info(
        f'- Points above expectation, summed over every player: '
        f'{sum(totals.values()):+.2f}'
    )
    print_interactive_info(
        f'- Worst player: {per_game[worst_id]:+.4f} points per game over '
        f'{games[worst_id]} games, which is {per_game[worst_id] * K_FACTOR:+.2f} '
        f'rating points per game at K={K_FACTOR}'
    )
    print_interactive_info(
        '- Per player, points per game: '
        + ', '.join(
            f'{value:+.3f}'
            for value in sorted(per_game.values(), key=abs, reverse=True)[:8]
        )
        + ' (the eight furthest from zero)'
    )
    # Whether a drift is bias or chance is not settled by its size: a score
    # of 0, a half or one against an expectation between them varies by
    # about 0.4 of a point a game, so the mean over n games wanders by
    # 0.4/sqrt(n) even when nothing is wrong. What separates the two is that
    # chance shrinks as the sample grows and bias does not, so the figure is
    # measured against that standard error rather than against a fixed
    # number. Three of them is generous for the worst of a field this size.
    standard_error = {
        player_id: GAME_DEVIATION / sqrt(games[player_id]) for player_id in per_game
    }
    print_interactive_info(
        f'- Expected to wander by {standard_error[worst_id]:.4f} points per game '
        f'on chance alone, over {games[worst_id]} games'
    )
    astray = {
        player_id: value
        for player_id, value in per_game.items()
        if abs(value) > 3 * standard_error[player_id]
    }
    if astray:
        print_interactive_error(
            f'- {len(astray)} player(s) beyond three times that, which is not '
            f'chance: the results are not being drawn from the ratings stated'
        )
        for player_id, value in sorted(
            astray.items(), key=lambda pair: abs(pair[1]), reverse=True
        )[:5]:
            print_interactive_error(
                f'    player {player_id}: {value:+.4f} against '
                f'{standard_error[player_id]:.4f}'
            )
        return 1
    print_interactive_info(
        '- Every player within three standard errors of expectation, so the '
        'drift is chance and not bias'
    )
    return 0


if __name__ == '__main__':
    sys.exit(
        main(
            int(sys.argv[1]) if len(sys.argv) > 1 else 100,
            int(sys.argv[2]) if len(sys.argv) > 2 else 40,
            int(sys.argv[3]) if len(sys.argv) > 3 else 9,
        )
    )
