"""The journal migration telling who acted apart from where from."""

import sqlite3

import pytest

from database.sqlite.migration import BaseMigration
from database.sqlite.event.migrations.m123_journal import (
    Migration as JournalMigration,
)
from database.sqlite.event.migrations.m124_journal_author_source import Migration


class Cursor:
    """Runs the migration's statements on a bare connection."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def execute(self, statement: str) -> None:
        self.connection.execute(statement)


def run[M: BaseMigration](
    migration_class: type[M], connection: sqlite3.Connection
) -> M:
    instance = migration_class.__new__(migration_class)
    instance.database = Cursor(connection)  # type: ignore[assignment]
    return instance


OLD_ENTRIES = [
    # actor_kind, actor_name, account_id, host
    ('administrator', None, 1, '127.0.0.1'),
    ('account', 'Jane ARBITER', 7, '192.168.1.25'),
    ('anonymous', None, None, '192.168.1.40'),
    ('screen', 'Result entry', None, '192.168.1.41'),
    ('plugin', 'Sharly-Chess.com', None, None),
    ('system', None, None, None),
]


def journal_with_old_entries() -> sqlite3.Connection:
    connection = sqlite3.connect(':memory:')
    run(JournalMigration, connection).forward()
    connection.executemany(
        'INSERT INTO `journal` (`at`, `action`, `actor_kind`, `actor_name`, '
        '`account_id`, `host`) VALUES (?, ?, ?, ?, ?, ?)',
        [('2026-11-19 10:00:00', 'note', *entry) for entry in OLD_ENTRIES],
    )
    return connection


@pytest.mark.unit
def test_each_entry_tells_who_and_where() -> None:
    connection = journal_with_old_entries()

    run(Migration, connection).forward()

    rows = connection.execute(
        'SELECT `author_kind`, `account_id`, `source_kind`, `source_name`, `host` '
        'FROM `journal` ORDER BY `id`'
    ).fetchall()
    assert rows == [
        ('administrator', 1, 'computer', None, '127.0.0.1'),
        ('account', 7, 'network', None, '192.168.1.25'),
        (None, None, 'network', None, '192.168.1.40'),
        (None, None, 'screen', 'Result entry', '192.168.1.41'),
        (None, None, 'plugin', 'Sharly-Chess.com', None),
        (None, None, 'application', None, None),
    ]


@pytest.mark.unit
def test_the_migration_rolls_back() -> None:
    connection = journal_with_old_entries()
    migration = run(Migration, connection)

    migration.forward()
    migration.backward()

    rows = connection.execute(
        'SELECT `actor_kind`, `actor_name`, `account_id`, `host` FROM `journal` '
        'ORDER BY `id`'
    ).fetchall()
    # A staff account is named by its id from then on.
    assert rows == [
        (kind, None if kind == 'account' else name, account_id, host)
        for kind, name, account_id, host in OLD_ENTRIES
    ]
