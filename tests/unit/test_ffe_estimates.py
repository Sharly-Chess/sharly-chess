import json

import pytest

from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.ffe.migrations.m010_prescribed_estimates import Migration
from plugins.ffe.utils import is_ffe_estimate


@pytest.mark.unit
@pytest.mark.parametrize(
    'value, expected',
    [
        (799, True),
        (999, True),
        (1199, True),
        (1299, True),
        (1399, True),
        (1499, False),
        (1300, False),
        (0, False),
    ],
)
def test_ffe_estimates_end_in_99_below_the_fide_floor(
    value: int, expected: bool
) -> None:
    assert is_ffe_estimate(value) == expected


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
