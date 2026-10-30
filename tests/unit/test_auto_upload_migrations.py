import json

import pytest

from database.sqlite.migration import BaseMigration
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.chess_results.migrations import (
    m001_tournament_auto_upload_only as chess_results_migration,
)
from plugins.ffe.migrations import m011_tournament_auto_upload_only as ffe_migration
from plugins.sce.migrations import m001_tournament_auto_upload_only as sce_migration


@pytest.mark.unit
@pytest.mark.parametrize(
    'plugin_id, migration_class',
    [
        ('sce', sce_migration.Migration),
        ('ffe', ffe_migration.Migration),
        ('chess_results', chess_results_migration.Migration),
    ],
)
@pytest.mark.parametrize(
    'event_auto_upload, expected',
    [
        (True, [True, False, None]),
        (False, [False, False, None]),
        (None, [True, False, None]),
    ],
)
def test_the_migration_moves_the_event_auto_upload_to_the_tournaments(
    tmp_path,
    plugin_id: str,
    migration_class: type[BaseMigration],
    event_auto_upload: bool | None,
    expected: list[bool | None],
) -> None:
    file = tmp_path / 'event.db'
    SQLiteDatabase(file, write=True)._create(
        'CREATE TABLE info (plugin_data TEXT);'
        'CREATE TABLE tournament (id INTEGER PRIMARY KEY, plugin_data TEXT)'
    )
    event_data: dict = {'remark': 'kept'}
    if event_auto_upload is not None:
        event_data['auto_upload'] = event_auto_upload
    tournament_plugin_data = [
        {plugin_id: {'auto_upload': True}},
        {plugin_id: {'auto_upload': False}},
        {},
    ]
    with SQLiteDatabase(file, write=True) as database:
        database.execute(
            'INSERT INTO info (plugin_data) VALUES (?)',
            (json.dumps({plugin_id: event_data}),),
        )
        for plugin_data in tournament_plugin_data:
            database.execute(
                'INSERT INTO tournament (plugin_data) VALUES (?)',
                (json.dumps(plugin_data),),
            )
        migration_class(database).forward()  # type: ignore[arg-type]
        database.execute('SELECT plugin_data FROM info')
        assert json.loads(database.fetchone()['plugin_data']) == {
            plugin_id: {'remark': 'kept'}
        }
        database.execute('SELECT plugin_data FROM tournament ORDER BY id')
        assert [
            json.loads(row['plugin_data']).get(plugin_id, {}).get('auto_upload')
            for row in database.fetchall()
        ] == expected
