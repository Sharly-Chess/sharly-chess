from itertools import chain

from data.screens.screen_set import ScreenSet
from utils.enum import BoardSelectionMode


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


def make_screen_set(
    first: int,
    last: int,
    columns: int = 1,
    mode: BoardSelectionMode = BoardSelectionMode.PAIRING,
    fixed_board_numbers: list[int] | None = None,
) -> ScreenSet:
    """A bare ScreenSet carrying just the attributes ``_extract_data`` reads,
    bypassing the heavy constructor (which needs a full event graph)."""
    screen_set = object.__new__(_BareScreenSet)
    screen_set.first = first
    screen_set.last = last
    screen_set.columns = columns
    screen_set.board_selection_mode = mode
    screen_set.fixed_board_numbers = fixed_board_numbers
    screen_set.items_lists = None
    screen_set.first_item = None
    screen_set.last_item = None
    return screen_set


def selected_numbers(screen_set: ScreenSet) -> list[int]:
    items_lists = screen_set.items_lists
    assert items_lists is not None
    return [board.number for board in chain.from_iterable(items_lists)]


# --- PAIRING mode (default): order and range are the pairing/standings order ---


def test_pairing_range_selects_by_position():
    # A fixed table (number 10) sits first in pairing (index) order. In pairing
    # mode the range is positional, so first/last 1–3 select the first three
    # boards in pairing order — the fixed board keeps its standings slot.
    boards = [FakeBoard(n) for n in (10, 1, 2, 3)]
    screen_set = make_screen_set(first=1, last=3)

    screen_set._extract_data(items=boards, extract_boards=True)

    assert selected_numbers(screen_set) == [10, 1, 2]


def test_pairing_range_preserves_pairing_order():
    boards = [FakeBoard(n) for n in (10, 1, 2, 3)]
    screen_set = make_screen_set(first=0, last=0)

    screen_set._extract_data(items=boards, extract_boards=True)

    assert selected_numbers(screen_set) == [10, 1, 2, 3]


def test_pairing_open_ended_range():
    boards = [FakeBoard(n) for n in (5, 1, 3, 2, 4)]
    # last unset -> from position 3 to the end
    screen_set = make_screen_set(first=3, last=0)

    screen_set._extract_data(items=boards, extract_boards=True)

    assert selected_numbers(screen_set) == [3, 2, 4]


# --- BOARD_NUMBER mode: order and range are the displayed table number ---


def test_board_number_range_selects_by_number_not_position():
    boards = [FakeBoard(n) for n in (10, 1, 2, 3)]
    screen_set = make_screen_set(first=1, last=3, mode=BoardSelectionMode.BOARD_NUMBER)

    screen_set._extract_data(items=boards, extract_boards=True)

    assert selected_numbers(screen_set) == [1, 2, 3]


def test_board_number_range_includes_highest_number_when_list_is_longer():
    # A range 1–71 must keep table 71 even though it is first in the list.
    boards = [FakeBoard(71)] + [FakeBoard(n) for n in range(1, 71)]  # 71 boards
    screen_set = make_screen_set(first=1, last=71, mode=BoardSelectionMode.BOARD_NUMBER)

    screen_set._extract_data(items=boards, extract_boards=True)

    assert selected_numbers(screen_set) == list(range(1, 72))


def test_board_number_orders_output_by_number():
    boards = [FakeBoard(n) for n in (10, 1, 2, 3)]
    screen_set = make_screen_set(first=0, last=0, mode=BoardSelectionMode.BOARD_NUMBER)

    screen_set._extract_data(items=boards, extract_boards=True)

    assert selected_numbers(screen_set) == [1, 2, 3, 10]


# --- SPECIFIC mode: an explicit list of board numbers, ordered by number ---


def test_specific_selects_listed_boards_ordered_by_number():
    boards = [FakeBoard(n) for n in (10, 1, 2, 3)]
    screen_set = make_screen_set(
        first=0,
        last=0,
        mode=BoardSelectionMode.SPECIFIC,
        fixed_board_numbers=[2, 10],
    )

    screen_set._extract_data(items=boards, extract_boards=True)

    assert selected_numbers(screen_set) == [2, 10]


# --- Players / rankings keep 1-based position semantics ---


def test_non_board_range_still_uses_position():
    items = ['a', 'b', 'c', 'd']
    screen_set = make_screen_set(first=1, last=2)

    screen_set._extract_data(items=items, extract_boards=False)

    items_lists = screen_set.items_lists
    assert items_lists is not None
    assert list(chain.from_iterable(items_lists)) == ['a', 'b']
