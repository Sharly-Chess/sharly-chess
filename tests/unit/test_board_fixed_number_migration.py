import pytest

from database.sqlite.event.migrations import (
    m123_freeze_board_fixed_numbers as migration,
)
from database.sqlite.sqlite_database import SQLiteDatabase


@pytest.mark.unit
def test_the_migration_freezes_the_fixed_number_of_the_boards(tmp_path) -> None:
    file = tmp_path / 'event.db'
    SQLiteDatabase(file, write=True)._create(
        'CREATE TABLE player (id INTEGER PRIMARY KEY, fixed INTEGER);'
        'CREATE TABLE board (id INTEGER PRIMARY KEY, white_player_id INTEGER, '
        'black_player_id INTEGER, fixed_number INTEGER)'
    )
    players = [(1, None), (2, 5), (3, 8), (4, 0)]
    boards = [
        (1, 1, None, None),
        (2, 2, 1, None),
        (3, 1, 3, None),
        (4, 2, 3, None),
        (5, 4, None, None),
        (6, 2, None, 0),
        (7, 1, None, 4),
    ]
    with SQLiteDatabase(file, write=True) as database:
        for player in players:
            database.execute('INSERT INTO player (id, fixed) VALUES (?, ?)', player)
        for board in boards:
            database.execute(
                'INSERT INTO board (id, white_player_id, black_player_id, '
                'fixed_number) VALUES (?, ?, ?, ?)',
                board,
            )
        migration.Migration(database).forward()  # type: ignore[arg-type]
        database.execute('SELECT fixed_number FROM board ORDER BY id')
        assert [row['fixed_number'] for row in database.fetchall()] == [
            0,
            5,
            8,
            8,
            0,
            0,
            4,
        ]
