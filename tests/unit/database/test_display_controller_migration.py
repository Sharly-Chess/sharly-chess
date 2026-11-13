"""The screens migration of this version, forwards and back."""

import sqlite3

from database.sqlite.event.migrations.m120_display_controller_items import Migration


class Cursor:
    """Runs the migration's statements on a bare connection."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def execute(self, statement: str) -> None:
        self.connection.execute(statement)


def columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f'PRAGMA table_info(`{table}`)')}


def migration(connection: sqlite3.Connection) -> Migration:
    instance = Migration.__new__(Migration)
    instance.database = Cursor(connection)  # type: ignore[assignment]
    return instance


def database() -> sqlite3.Connection:
    connection = sqlite3.connect(':memory:')
    connection.execute('PRAGMA foreign_keys=ON')
    for table in ('screen', 'family'):
        connection.execute(
            f'CREATE TABLE `{table}` (`id` INTEGER PRIMARY KEY, `type` TEXT)'
        )
        connection.executemany(
            f'INSERT INTO `{table}` (`type`) VALUES (?)',
            [('input',), ('check-in',), ('boards',), ('players',)],
        )
    connection.execute('CREATE TABLE `rotator` (`id` INTEGER PRIMARY KEY)')
    connection.execute(
        'CREATE TABLE `menu` (`id` INTEGER PRIMARY KEY, `default_type` TEXT)'
    )
    connection.execute("INSERT INTO `menu` (`default_type`) VALUES ('input')")
    connection.execute(
        'CREATE TABLE `menu_item` (`id` INTEGER PRIMARY KEY, `screen_type` TEXT)'
    )
    connection.execute("INSERT INTO `menu_item` (`screen_type`) VALUES ('input')")
    connection.execute(
        'CREATE TABLE `display_controller` (`id` INTEGER PRIMARY KEY, `name` TEXT)'
    )
    connection.execute('CREATE TABLE `info` (`name` TEXT)')
    return connection


def test_the_migration_runs_forwards_and_back() -> None:
    connection = database()
    before = {
        table: columns(connection, table)
        for table in ('display_controller', 'screen', 'family', 'info')
    }

    migration(connection).forward()
    assert {'family_id', 'family_page', 'menu_id'} <= columns(
        connection, 'display_controller'
    )
    assert {'screen_id', 'family_id', 'rotator_id', 'menu_id'} <= columns(
        connection, 'display_controller_item'
    )
    assert 'screens_fake_data' in columns(connection, 'info')
    for table in ('screen', 'family'):
        assert {'ranking_hidden_columns', 'check_in_show_members'} <= columns(
            connection, table
        )
    assert {'round_robin_grid_by_rank', 'round_robin_grid_players'} <= columns(
        connection, 'screen'
    )

    migration(connection).backward()
    for table, table_columns in before.items():
        assert columns(connection, table) == table_columns
    assert not columns(connection, 'display_controller_item')


def test_results_entry_screens_become_pairings_screens_accepting_input() -> None:
    connection = database()
    migration(connection).forward()
    for table in ('screen', 'family'):
        assert list(
            connection.execute(
                f'SELECT `type`, `accepts_input` FROM `{table}` ORDER BY `id`'
            )
        ) == [('boards', 1), ('check-in', 1), ('boards', 0), ('players', 0)]
    assert list(connection.execute('SELECT `screen_type` FROM `menu_item`')) == [
        ('boards',)
    ]
    assert list(connection.execute('SELECT `default_type` FROM `menu`')) == [
        ('boards',)
    ]

    migration(connection).backward()
    for table in ('screen', 'family'):
        assert [
            row[0]
            for row in connection.execute(f'SELECT `type` FROM `{table}` ORDER BY `id`')
        ] == ['input', 'check-in', 'boards', 'players']
