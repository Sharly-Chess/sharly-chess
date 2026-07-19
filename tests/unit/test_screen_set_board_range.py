from itertools import chain

from data.screen_set import ScreenSet


class FakeBoard:
    """Stands in for a Board — ``_extract_data`` only reads ``number`` when
    selecting a board range."""

    def __init__(self, number: int):
        self.number = number

    def __repr__(self) -> str:
        return f'FakeBoard({self.number})'


class _BareScreenSet(ScreenSet):
    """ScreenSet with ``columns`` overridden as a plain attribute so the
    instance can be built without the full event graph (``columns`` is
    normally a property that reads the screen)."""

    columns = 1


def make_screen_set(first: int, last: int, columns: int = 1) -> ScreenSet:
    """A bare ScreenSet carrying just the attributes ``_extract_data`` reads,
    bypassing the heavy constructor (which needs a full event graph)."""
    screen_set = object.__new__(_BareScreenSet)
    screen_set.first = first
    screen_set.last = last
    screen_set.columns = columns
    screen_set.fixed_board_numbers = None
    screen_set.items_lists = None
    screen_set.first_item = None
    screen_set.last_item = None
    return screen_set


def selected_numbers(screen_set: ScreenSet) -> list[int]:
    return [board.number for board in chain.from_iterable(screen_set.items_lists)]


def test_board_range_selects_by_number_not_position():
    # A fixed table (number 10) sits first in board (index) order, so number
    # no longer matches position. A range of tables 1–3 must select boards
    # numbered 1, 2, 3 — not the first three boards in the list.
    boards = [FakeBoard(n) for n in (10, 1, 2, 3)]
    screen_set = make_screen_set(first=1, last=3)

    screen_set._extract_data(items=boards, extract_boards=True)

    assert selected_numbers(screen_set) == [1, 2, 3]


def test_board_range_includes_highest_number_when_list_is_longer():
    # The reported bug: range 1–71 dropped table 71 and kept a low-numbered
    # fixed table, because the slice was capped at the board *count*.
    boards = [FakeBoard(71)] + [FakeBoard(n) for n in range(1, 71)]  # 71 boards
    screen_set = make_screen_set(first=1, last=71)

    screen_set._extract_data(items=boards, extract_boards=True)

    assert sorted(selected_numbers(screen_set)) == list(range(1, 72))


def test_open_ended_board_range():
    boards = [FakeBoard(n) for n in (5, 1, 3, 2, 4)]
    # last unset -> up to the highest number
    screen_set = make_screen_set(first=3, last=0)

    screen_set._extract_data(items=boards, extract_boards=True)

    assert sorted(selected_numbers(screen_set)) == [3, 4, 5]


def test_non_board_range_still_uses_position():
    # Players / rankings keep 1-based position semantics: first two items.
    items = ['a', 'b', 'c', 'd']
    screen_set = make_screen_set(first=1, last=2)

    screen_set._extract_data(items=items, extract_boards=False)

    assert list(chain.from_iterable(screen_set.items_lists)) == ['a', 'b']
