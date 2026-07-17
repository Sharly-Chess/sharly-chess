from data.board import Board, compute_round_board_numbers


class FakePlayer:
    def __init__(self, id_, fixed):
        self.id = id_
        self.fixed = fixed


class FakeStoredBoard:
    def __init__(self, id_, index, white_player_id, black_player_id):
        self.id = id_
        self.index = index
        self.white_player_id = white_player_id
        self.black_player_id = black_player_id


class FakeTournament:
    def __init__(self, players):
        self.tournament_players_by_id = {player.id: player for player in players}


def board_with(white_fixed, black_fixed, index=0, board_id=1):
    """Build a real ``Board`` between two players (both present) with the
    given fixed numbers. Returns ``(board, keepalive)`` — the caller must hold
    ``keepalive`` because the board only keeps weak references."""
    white = FakePlayer(1, white_fixed)
    black = FakePlayer(2, black_fixed)
    tournament = FakeTournament([white, black])
    stored = FakeStoredBoard(board_id, index, white.id, black.id)
    board = Board(tournament, 1, stored)
    return board, (tournament, white, black)


def numbers(entries, first_board_number=1, leave_holes=False):
    """Return the display numbers in board index order."""
    result = compute_round_board_numbers(entries, first_board_number, leave_holes)
    return [result[identifier] for identifier, _fixed, _standard in entries]


def entries_from(fixed_numbers, first_board_number=1):
    """Build ``(identifier, fixed_number, standard_number)`` tuples for a round
    where board *i* (index order) has the given fixed number or ``None``."""
    return [
        (index, fixed, first_board_number + index)
        for index, fixed in enumerate(fixed_numbers)
    ]


def test_no_fixed_players_is_plain_sequence():
    entries = entries_from([None, None, None, None])
    assert numbers(entries) == [1, 2, 3, 4]


def test_compact_reuses_the_displaced_table():
    # Board at index 3 has a player fixed to table 2. Compact numbering hands
    # table 2 to that board and fills 1, 3, 4 elsewhere: no hole, no duplicate.
    entries = entries_from([None, None, None, 2])
    assert numbers(entries) == [1, 3, 4, 2]
    assert sorted(numbers(entries)) == [1, 2, 3, 4]


def test_hole_mode_matches_legacy_behaviour():
    # Same round in hole mode: the fixed board takes 2, the natural table-2
    # board keeps 2 (duplicate) and the fixed board's own table (4) is a hole.
    entries = entries_from([None, None, None, 2])
    assert numbers(entries, leave_holes=True) == [1, 2, 3, 2]


def test_fixed_number_out_of_range_is_honoured():
    entries = entries_from([None, None, 100])
    assert numbers(entries) == [1, 2, 100]


def test_clashing_fixed_numbers_first_index_wins():
    # Two boards fixed to table 2: the earlier index keeps it, the later one
    # falls back to the next free number.
    entries = entries_from([2, None, 2])
    assert numbers(entries) == [2, 1, 3]


def test_first_board_number_offset_is_respected():
    entries = entries_from([None, None, None], first_board_number=101)
    assert numbers(entries, first_board_number=101) == [101, 102, 103]


def test_fixed_within_offset_range_stays_compact():
    entries = entries_from([None, 102, None], first_board_number=101)
    assert numbers(entries, first_board_number=101) == [101, 102, 103]


def test_two_fixed_players_facing_each_other_take_the_higher_number():
    board, _keep = board_with(3, 5)
    assert board.fixed_number == 5
    board, _keep = board_with(7, 2)
    assert board.fixed_number == 7


def test_one_fixed_player_facing_a_free_player():
    board, _keep = board_with(4, None)
    assert board.fixed_number == 4
    board, _keep = board_with(None, 4)
    assert board.fixed_number == 4


def test_no_fixed_player_on_the_board():
    board, _keep = board_with(None, None)
    assert board.fixed_number is None


def test_facing_fixed_players_are_numbered_once_in_a_compact_round():
    # Board index 2 has both players fixed (to 3 and 5) so it resolves to 5
    # and claims a single table; the round has no duplicate for the pair.
    board, _keep = board_with(3, 5, index=2, board_id=3)
    entries = [
        (1, None, 1),
        (2, None, 2),
        (board.identifier, board.fixed_number, 3),
    ]
    result = compute_round_board_numbers(entries, 1, leave_holes=False)
    assert result[board.identifier] == 5
    assert sorted(result.values()) == [1, 2, 5]
