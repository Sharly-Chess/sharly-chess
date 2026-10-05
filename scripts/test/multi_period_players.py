"""The players of a generated multi-period event, and the schedule they
play on.

Shared by the generators of an individual and of a team event, which
differ in what they hang the players on and not in the players
themselves. Imported after ``init_script()`` has run, as the project
imports below need it.
"""

import random
from datetime import date, datetime, time, timedelta

from data.tournament_period import MAX_PERIOD_DAYS
from database.sqlite.event.event_store import StoredPlayer
from utils.enum import TournamentRating

LAST_NAMES = [
    'DUPONT',
    'MARTIN',
    'BERNARD',
    'PETIT',
    'MOREAU',
    'LAURENT',
    'SIMON',
    'MICHEL',
    'LEFEVRE',
    'GARCIA',
    'ROUX',
    'FOURNIER',
    'GIRARD',
    'ANDRE',
    'MERCIER',
    'BLANC',
    'GUERIN',
    'MULLER',
    'HENRY',
    'ROUSSEAU',
]
FIRST_NAMES = [
    'Camille',
    'Alex',
    'Sam',
    'Noa',
    'Yann',
    'Iris',
    'Rémi',
    'Lou',
    'Anouk',
    'Théo',
    'Maël',
    'Jade',
    'Enzo',
    'Nina',
    'Hugo',
    'Zoé',
    'Lucas',
    'Eva',
    'Nathan',
    'Manon',
]
FIRST_FIDE_ID = 20600001


def round_datetime(round_nb: int, rounds: int, interval: int) -> datetime:
    """The day of a round, counted so that the tournament is half played."""
    offset = interval * (round_nb - 1 - rounds // 2)
    return datetime.combine(date.today() + timedelta(days=offset), time(14, 0))


def build_player(
    index: int, period_count: int, generator: random.Random
) -> tuple[StoredPlayer, list[dict[int, dict[str, int | None]]]]:
    """A player and the ratings of each slice after the first.

    Every rating a player can hold moves, by a few points from one slice
    to the next, and each stands still often enough that the fallback to
    the previous slice is exercised too. A slice records the whole of the
    player's ratings, so an unmoved one is repeated.

    One player in four is unrated and carries the arbiter's estimate
    alone, which they may revise between slices; the rated ones keep an
    estimate too, as a player entered before their rating was known
    does."""
    unrated = index % 4 == 3
    fide_rating: int | None = None if unrated else generator.randrange(1100, 2300, 5)
    national_rating: int | None = (
        None if fide_rating is None else fide_rating + generator.randrange(-60, 60, 5)
    )
    estimated_rating = (
        generator.randrange(900, 1600, 25)
        if fide_rating is None
        else fide_rating + generator.randrange(-40, 40, 10)
    )
    k_factor: int | None = None
    if fide_rating is not None:
        k_factor = 40 if fide_rating < 1600 else (20 if fide_rating < 2100 else 10)

    def ratings() -> dict[int, dict[str, int | None]]:
        return {
            TournamentRating.STANDARD.value: {
                'fide': fide_rating,
                'national': national_rating,
                'estimated': estimated_rating,
                'k': k_factor,
            }
        }

    stored_player = StoredPlayer(
        id=None,
        last_name=LAST_NAMES[index % len(LAST_NAMES)],
        first_name=FIRST_NAMES[(index * 7) % len(FIRST_NAMES)],
        gender=generator.choice(['M', 'F']),
        year_of_birth=generator.randint(1960, 2014),
        fide_id=None if unrated else FIRST_FIDE_ID + index,
        federation='FRA',
        ratings=ratings(),
    )
    period_ratings: list[dict[int, dict[str, int | None]]] = []
    for _period_index in range(period_count - 1):
        if fide_rating is not None and generator.random() < 0.7:
            fide_rating += generator.choice([-14, -9, -5, 4, 7, 12, 18])
        if national_rating is not None and generator.random() < 0.7:
            national_rating += generator.choice([-20, -11, -6, 5, 9, 15, 22])
        if generator.random() < 0.4:
            estimated_rating += generator.choice([-50, -25, 25, 50])
        period_ratings.append(ratings())
    return stored_player, period_ratings


def parse_period_first_rounds(values: list[int], rounds: int) -> list[int]:
    """The rounds the periods start at, as the tournament form reads them:
    round 1 always starts one, and a boundary past the last round is
    dropped."""
    return sorted({1} | {value for value in values if 1 < value <= rounds})


def period_lines(
    period_first_rounds: list[int],
    rounds: int,
    round_datetimes: dict[int, datetime],
) -> list[str]:
    """One line per slice, saying what it covers and whether FIDE would
    take it."""
    boundaries = [*period_first_rounds, rounds + 1]
    lines: list[str] = []
    for index, first_round in enumerate(period_first_rounds):
        last_round = boundaries[index + 1] - 1
        start_date = round_datetimes[first_round].date()
        stop_date = round_datetimes[last_round].date()
        days = (stop_date - start_date).days + 1
        current = start_date <= date.today() <= stop_date
        too_long = ' — LONGER THAN FIDE ALLOWS' if days > MAX_PERIOD_DAYS else ''
        lines.append(
            f'  period {index + 1}: R{first_round}-R{last_round} '
            f'{start_date} -> {stop_date} ({days} days)'
            + (' <- being played' if current else '')
            + too_long
        )
    return lines
