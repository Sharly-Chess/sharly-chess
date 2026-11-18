import json

import pytest

from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.sce.sce_data import SCEPlayerPluginData
from plugins.sce.migrations import m002_drop_player_is_duplicated as migration


@pytest.mark.unit
def test_the_migration_drops_the_duplicate_flag_of_the_players(tmp_path) -> None:
    file = tmp_path / 'event.db'
    SQLiteDatabase(file, write=True)._create(
        'CREATE TABLE player (id INTEGER PRIMARY KEY, plugin_data TEXT)'
    )
    players_plugin_data = [
        {'sce': {'id': None, 'is_duplicated': True}},
        {'sce': {'id': 'r1', 'is_duplicated': False}},
        {'sce': {'duplicated_registration_id': 'r2', 'is_duplicated': False}},
        {'ffe': {'is_duplicated': True}},
        {},
    ]
    with SQLiteDatabase(file, write=True) as database:
        for plugin_data in players_plugin_data:
            database.execute(
                'INSERT INTO player (plugin_data) VALUES (?)',
                (json.dumps(plugin_data),),
            )
        migration.Migration(database).forward()  # type: ignore[arg-type]
        database.execute('SELECT plugin_data FROM player ORDER BY id')
        migrated = [json.loads(row['plugin_data']) for row in database.fetchall()]
    assert migrated == [
        {'sce': {'id': None}},
        {'sce': {'id': 'r1'}},
        {'sce': {'duplicated_registration_id': 'r2'}},
        {'ffe': {'is_duplicated': True}},
        {},
    ]
    assert [
        SCEPlayerPluginData.from_stored_value(data['sce']).is_duplicated
        for data in migrated[:3]
    ] == [False, False, True]
