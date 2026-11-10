import json

import pytest

from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.ffe.migrations.m010_prescribed_estimates import Migration
from plugins.ffe.utils import ffe_estimate_rating, ffe_list_ratings, is_ffe_estimate
from utils.enum import Cadence, PlayerRatingType
from utils.types import RatingOrigin


@pytest.mark.unit
@pytest.mark.parametrize(
    'value, expected',
    [
        (799, True),
        (1099, True),
        (1399, True),
        (1449, True),
        (1749, True),
        (1300, False),
        (1450, False),
        (1643, False),
        (0, False),
    ],
)
def test_ffe_estimates_go_by_steps_of_50_ending_in_49_or_99(
    value: int, expected: bool
) -> None:
    assert is_ffe_estimate(value) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    'value, rating_type, expected',
    [
        (799, PlayerRatingType.NATIONAL, {}),
        (999, PlayerRatingType.NATIONAL, {}),
        (799, PlayerRatingType.ESTIMATED, {}),
        (1199, PlayerRatingType.NATIONAL, {'manual': 1199}),
        (1399, PlayerRatingType.NATIONAL, {'manual': 1399}),
        (1399, PlayerRatingType.ESTIMATED, {'manual': 1399}),
        (1749, PlayerRatingType.NATIONAL, {'manual': 1749}),
        (1500, PlayerRatingType.ESTIMATED, {'manual': 1500}),
        (860, PlayerRatingType.NATIONAL, {'national': 860}),
        (1643, PlayerRatingType.NATIONAL, {'national': 1643}),
        (1399, PlayerRatingType.FIDE, {'fide': 1399}),
    ],
)
def test_the_ffe_list_estimates_are_kept_however_typed_but_outgrown_ones(
    value: int, rating_type: PlayerRatingType, expected: dict[str, int]
) -> None:
    ratings = ffe_list_ratings(
        {Cadence.RAPID: (value, rating_type)}, RatingOrigin('ffe')
    )
    rating = ratings[Cadence.RAPID.value]
    rating.pop('origins', None)
    assert rating == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    'value, cadence, expected',
    [
        (1299, Cadence.STANDARD, {}),
        (1399, Cadence.STANDARD, {'manual': 1399}),
        (1499, Cadence.STANDARD, {'manual': 1499}),
        (799, Cadence.RAPID, {}),
        (999, Cadence.BLITZ, {}),
        (1199, Cadence.BLITZ, {'manual': 1199}),
        (1099, Cadence.RAPID, {'manual': 1099}),
        (1399, Cadence.RAPID, {'manual': 1399}),
    ],
)
def test_the_estimates_of_a_younger_category_are_left_to_the_age_rule(
    value: int, cadence: Cadence, expected: dict[str, int]
) -> None:
    assert ffe_estimate_rating(value, cadence).stored_value == expected


@pytest.mark.unit
@pytest.mark.parametrize('enabled_plugins, dropped', [(['ffe'], True), ([], False)])
def test_the_migration_drops_the_ffe_estimates_of_the_events_of_the_plugin(
    tmp_path, enabled_plugins: list[str], dropped: bool
) -> None:
    file = tmp_path / 'event.db'
    SQLiteDatabase(file, write=True)._create(
        'CREATE TABLE info (enabled_plugins TEXT);'
        'CREATE TABLE player (id INTEGER PRIMARY KEY, ratings TEXT);'
        'CREATE TABLE player_period (id INTEGER PRIMARY KEY, ratings TEXT)'
    )
    ratings = {
        '1': {'manual': 1299, 'pinned': 'fide:1'},
        '2': {'manual': 799},
        '3': {'manual': 1450},
        '4': {'manual': 1499, 'national': 1520},
    }
    expected = (
        {
            '1': {'pinned': 'fide:1'},
            '2': {},
            '3': {'manual': 1450},
            '4': {'manual': 1499, 'national': 1520},
        }
        if dropped
        else ratings
    )
    with SQLiteDatabase(file, write=True) as database:
        database.execute(
            'INSERT INTO info (enabled_plugins) VALUES (?)',
            (json.dumps(enabled_plugins),),
        )
        for table in ('player', 'player_period'):
            database.execute(
                f'INSERT INTO {table} (id, ratings) VALUES (1, ?)',
                (json.dumps(ratings),),
            )
        Migration(database).forward()  # type: ignore[arg-type]
        for table in ('player', 'player_period'):
            database.execute(f'SELECT ratings FROM {table}')
            assert json.loads(database.fetchone()['ratings']) == expected
