"""The timer hours migration of this version, forwards and back."""

import sqlite3
from collections.abc import Iterator
from typing import Any

from database.sqlite.event.migrations.m121_timer_hour_kinds import Migration


class Cursor:
    """Runs the migration's statements on a bare connection."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.cursor = connection.cursor()

    def execute(self, statement: str, params: tuple[Any, ...] = ()) -> None:
        self.cursor.execute(statement, params)

    def fetchall(self) -> Iterator[dict[str, Any]]:
        names = [column[0] for column in self.cursor.description]
        for row in self.cursor.fetchall():
            yield dict(zip(names, row, strict=True))


def migration(connection: sqlite3.Connection) -> Migration:
    instance = Migration.__new__(Migration)
    instance.database = Cursor(connection)  # type: ignore[assignment]
    return instance


def database() -> sqlite3.Connection:
    connection = sqlite3.connect(':memory:')
    connection.execute('CREATE TABLE `timer` (`id` INTEGER PRIMARY KEY)')
    connection.execute('INSERT INTO `timer` (`id`) VALUES (1)')
    connection.execute(
        'CREATE TABLE `timer_hour` ('
        '    `id` INTEGER NOT NULL,'
        '    `uniq_id` TEXT NOT NULL,'
        '    `timer_id` INTEGER NOT NULL,'
        '    `text_before` TEXT,'
        '    `text_after` TEXT,'
        '    `triggered_at` TEXT,'
        '    PRIMARY KEY(`id` AUTOINCREMENT),'
        '    UNIQUE(`timer_id`, `uniq_id`),'
        '    FOREIGN KEY (`timer_id`) REFERENCES `timer`(`id`) ON DELETE CASCADE'
        ')'
    )
    connection.executemany(
        'INSERT INTO `timer_hour` (`uniq_id`, `timer_id`, `text_before`, '
        '`text_after`, `triggered_at`) VALUES (?, 1, ?, ?, ?)',
        [
            ('3', '', '', '2026-11-14T13:00:00+00:00'),
            (
                'Check-in',
                'Check-in in %s',
                'Check-in open',
                '2026-11-14T08:00:00+00:00',
            ),
        ],
    )
    return connection


def hours(connection: sqlite3.Connection, columns: str) -> list[tuple[Any, ...]]:
    return connection.execute(
        f'SELECT {columns} FROM `timer_hour` ORDER BY `id`'
    ).fetchall()


def test_a_number_becomes_a_round_and_any_other_text_a_label() -> None:
    connection = database()
    migration(connection).forward()
    assert hours(connection, '`round`, `label`, `text_before`') == [
        (3, None, ''),
        (None, 'Check-in', 'Check-in in %s'),
    ]


def test_two_hours_may_share_a_label_once_migrated() -> None:
    connection = database()
    migration(connection).forward()
    connection.execute(
        'INSERT INTO `timer_hour` (`timer_id`, `label`, `triggered_at`) '
        "VALUES (1, 'Check-in', '2026-11-15T08:00:00+00:00')"
    )
    assert len(hours(connection, '`id`')) == 3


def test_the_migration_goes_back_with_unique_texts() -> None:
    connection = database()
    migration(connection).forward()
    connection.execute(
        'INSERT INTO `timer_hour` (`timer_id`, `label`, `triggered_at`) '
        "VALUES (1, 'Check-in', '2026-11-15T08:00:00+00:00')"
    )
    migration(connection).backward()
    assert hours(connection, '`uniq_id`') == [
        ('3',),
        ('Check-in',),
        ('Check-in (2)',),
    ]
