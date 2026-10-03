"""The national identifier of the players: which data source it belongs
to, and how the data sources recognise it."""

import pytest

from data.input_output.national_data_sources import (
    CfcDataSource,
    FsiDataSource,
    KnsbDataSource,
    NATIONAL_DATA_SOURCE_TYPES,
)
from database.sqlite.event.event_store import StoredPlayer


def _player(national_id: str | None, national_source: str | None) -> StoredPlayer:
    return StoredPlayer(
        id=None, last_name='X', national_id=national_id, national_source=national_source
    )


@pytest.mark.unit
def test_national_data_sources_are_keyed_on_their_federation() -> None:
    assert KnsbDataSource.federation == 'NED'
    assert KnsbDataSource.national_source_id == 'knsb'
    assert KnsbDataSource.static_id() == 'knsb'
    assert FsiDataSource.federation == 'ITA'
    assert CfcDataSource.national_source_id == 'cfc'
    assert len({source.static_id() for source in NATIONAL_DATA_SOURCE_TYPES}) == len(
        NATIONAL_DATA_SOURCE_TYPES
    )
    assert len({source.federation for source in NATIONAL_DATA_SOURCE_TYPES}) == len(
        NATIONAL_DATA_SOURCE_TYPES
    )


@pytest.mark.unit
def test_an_identifier_matches_within_its_source() -> None:
    source = KnsbDataSource()
    assert source.check_player_match(_player('12', 'knsb'), _player('12', 'knsb'))
    assert source.check_player_match(_player('12', None), _player('12', 'knsb'))
    assert not source.check_player_match(_player('12', 'fsi'), _player('12', 'knsb'))
    assert not source.check_player_match(_player('12', 'knsb'), _player('13', 'knsb'))
    assert not source.check_player_match(_player(None, None), _player(None, 'knsb'))


@pytest.mark.unit
def test_the_profile_link_names_the_federation() -> None:
    assert KnsbDataSource().national_source_name == 'KNSB'
    assert FsiDataSource().national_source_name == 'FSI'


EVENT_ID = 'test-national-id'


@pytest.mark.unit
def test_the_identifier_and_its_source_are_stored_with_the_player() -> None:
    from database.sqlite.event.event_database import EventDatabase
    from tests.test_config import TestUtils

    TestUtils.create_event(EVENT_ID)
    try:
        with EventDatabase(EVENT_ID, write=True) as database:
            player_id = database.add_stored_player(
                StoredPlayer(
                    id=None,
                    last_name='NYBÄCK',
                    national_id='5239',
                    national_source='ssl',
                )
            )
            database.add_stored_player(StoredPlayer(id=None, last_name='DOE'))
        with EventDatabase(EVENT_ID) as database:
            players = {player.id: player for player in database.load_stored_players()}
        assert (players[player_id].national_id, players[player_id].national_source) == (
            '5239',
            'ssl',
        )
        doe = next(player for player in players.values() if player.last_name == 'DOE')
        assert (doe.national_id, doe.national_source) == (None, None)
    finally:
        TestUtils.delete_event(EVENT_ID)


@pytest.mark.unit
def test_the_ffe_licence_number_of_the_players_becomes_their_national_id(
    tmp_path,
) -> None:
    from database.sqlite.sqlite_database import SQLiteDatabase
    from plugins.ffe.migrations.m008_player_licence_number_as_national_id import (
        Migration,
    )

    file = tmp_path / 'event.db'
    SQLiteDatabase(file, write=True)._create(
        'CREATE TABLE player (id INTEGER PRIMARY KEY, plugin_data TEXT, '
        'national_id TEXT, national_source TEXT)'
    )
    with SQLiteDatabase(file, write=True) as database:
        database.executemany(
            'INSERT INTO player (plugin_data, national_id, national_source) '
            'VALUES (?, ?, ?)',
            [
                (
                    '{"ffe": {"ffe_id": 12345, "ffe_licence_number": "R08943", '
                    '"ffe_licence": "A"}}',
                    None,
                    None,
                ),
                ('{"ffe": {"ffe_licence": "B"}}', None, None),
                ('{"ffe": {"ffe_licence_number": "X00001"}}', '9', 'knsb'),
                (None, None, None),
            ],
        )
        migration = Migration(database)  # type: ignore[arg-type]
        migration.forward()
        database.execute(
            'SELECT plugin_data, national_id, national_source FROM player ORDER BY id'
        )
        assert list(database.fetchall()) == [
            {
                'plugin_data': '{"ffe":{"ffe_id":12345,"ffe_licence":"A"}}',
                'national_id': 'R08943',
                'national_source': 'ffe',
            },
            {
                'plugin_data': '{"ffe": {"ffe_licence": "B"}}',
                'national_id': None,
                'national_source': None,
            },
            {
                'plugin_data': '{"ffe":{}}',
                'national_id': '9',
                'national_source': 'knsb',
            },
            {'plugin_data': None, 'national_id': None, 'national_source': None},
        ]
        migration.backward()
        database.execute('SELECT plugin_data, national_id FROM player ORDER BY id')
        rows = list(database.fetchall())
        assert rows[0] == {
            'plugin_data': (
                '{"ffe":{"ffe_id":12345,"ffe_licence":"A","ffe_licence_number":"R08943"}}'
            ),
            'national_id': None,
        }
        assert rows[2]['national_id'] == '9'
