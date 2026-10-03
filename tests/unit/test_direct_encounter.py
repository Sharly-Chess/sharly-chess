"""Direct encounter (C.07 Art. 6), for individuals and teams alike."""

from collections.abc import Sequence

import pytest

from data.tie_breaks.direct_encounter import rank_by_encounters


def _min_max(results: dict[tuple[str, str], float]):
    """The lowest and highest score of a player against the group, a game
    missing between them counting 0 or 1."""

    def min_max(player: str, group: Sequence[str]) -> tuple[float, float]:
        scored = 0.0
        missing = 0
        for other in group:
            if other == player:
                continue
            if (player, other) in results:
                scored += results[(player, other)]
            else:
                missing += 1
        return scored, scored + missing

    return min_max


def _games(*games: tuple[str, str, float]) -> dict[tuple[str, str], float]:
    results = {}
    for white, black, score in games:
        results[(white, black)] = score
        results[(black, white)] = 1 - score
    return results


@pytest.mark.unit
def test_when_all_have_met_the_encounters_place_everyone():
    results = _games(('A', 'B', 1), ('A', 'C', 1), ('B', 'C', 0.5))
    values: dict[str, int] = {}
    rank_by_encounters(['A', 'B', 'C'], _min_max(results), values)
    assert values == {'A': 2, 'B': 0, 'C': 0}


@pytest.mark.unit
def test_with_games_missing_and_nobody_alone_on_top_the_group_stays_level():
    # D has not met A or B, and could still score 2.5 against the group,
    # above the 2 A is sure of: nobody is placed.
    results = _games(('A', 'B', 1), ('A', 'C', 1), ('B', 'C', 0.5), ('C', 'D', 0.5))
    values: dict[str, int] = {}
    rank_by_encounters(['A', 'B', 'C', 'D'], _min_max(results), values)
    assert values == {'A': 0, 'B': 0, 'C': 0, 'D': 0}


@pytest.mark.unit
def test_the_rest_is_ranked_again_once_the_leader_is_placed():
    # Art. 6.3: "Article 6 shall then be reapplied to all remaining unranked
    # participants". Once A is placed, B, C and D have all met, and the
    # standings between them put D last.
    results = _games(
        ('A', 'B', 1), ('A', 'C', 1), ('B', 'C', 0.5), ('B', 'D', 1), ('C', 'D', 1)
    )
    values: dict[str, int] = {}
    rank_by_encounters(['A', 'B', 'C', 'D'], _min_max(results), values)
    assert values == {'A': 3, 'B': 1, 'C': 1, 'D': 0}


@pytest.mark.unit
def test_the_next_rank_is_placed_on_the_same_standings():
    # Art. 6.3: "the same applies to the second rank when the first is
    # assigned this way; and so on". B has 2.5 and is placed; on the same
    # standings C has 2, above the 1.5 A can reach and the 1 D can: C is
    # second. A and D, who never met, are left level.
    results = _games(
        ('B', 'C', 0.5), ('B', 'D', 1), ('B', 'A', 1), ('A', 'C', 0.5), ('C', 'D', 1)
    )
    values: dict[str, int] = {}
    rank_by_encounters(['A', 'B', 'C', 'D'], _min_max(results), values)
    assert values == {'A': 0, 'B': 3, 'C': 2, 'D': 0}


@pytest.mark.unit
def test_the_rest_is_ranked_together_when_they_have_all_met():
    # A has not met D, and beat B and C; B beat D, C drew with B and D. A is
    # placed; B (1.5), C (1) and D (0.5) have all met and are placed by their
    # standings among the three, C above D although the two drew.
    results = _games(
        ('A', 'B', 1), ('A', 'C', 1), ('B', 'D', 1), ('C', 'B', 0.5), ('C', 'D', 0.5)
    )
    values: dict[str, int] = {}
    rank_by_encounters(['A', 'B', 'C', 'D'], _min_max(results), values)
    assert values == {'A': 3, 'B': 2, 'C': 1, 'D': 0}


@pytest.mark.unit
def test_a_group_left_level_goes_to_the_fallback():
    results = _games(('A', 'B', 0.5))
    values: dict[str, int] = {}
    handed_over: list[tuple[list[str], int]] = []
    rank_by_encounters(
        ['A', 'B'],
        _min_max(results),
        values,
        min_value=4,
        fallback=lambda group, min_value: handed_over.append((list(group), min_value)),
    )
    assert handed_over == [(['A', 'B'], 4)]
    assert values == {}


def _table(*rows: tuple[float | None, ...]) -> dict[tuple[str, str], float]:
    """A crosstable, players numbered from 1, None for a game not played
    and for the diagonal."""
    results = {}
    for row_index, row in enumerate(rows):
        for column_index, score in enumerate(row):
            if score is not None:
                results[(str(row_index + 1), str(column_index + 1))] = score
    return results


_SEVEN = (
    (None, 0.5, 1, 1, 0.5, 0, 1),
    (0.5, None, 1, 1, 0.5, 0.5, 1),
    (0, 0, None, 1, 1, 1, 1),
    (0, 0, 0, None, 1, 1, 0.5),
    (0.5, 0.5, 0, 0, None, 1, 1),
    (1, 0.5, 0, 0, 0, None, 1),
    (0, 0, 0, 0.5, 0, 0, None),
)


@pytest.mark.unit
def test_seven_who_have_all_met_are_placed_by_art_6_2():
    """Otto Milvang, "Direct Encounter" (2026), table 3: 2 on 4.5; 1 and 3
    on 4, 1 having beaten 3; 5 on 3; 4 and 6 on 2.5, 4 having beaten 6."""
    values: dict[str, int] = {}
    rank_by_encounters(list('1234567'), _min_max(_table(*_SEVEN)), values)
    assert values == {'2': 6, '1': 5, '3': 4, '5': 3, '4': 2, '6': 1, '7': 0}


@pytest.mark.unit
def test_a_leader_the_missing_game_cannot_catch_is_placed():
    """Otto Milvang, "Direct Encounter" (2026), table 5: 1 beat 2 and 3, who
    have not met and can reach 1 at most."""
    results = _table((None, 1, 1), (0, None, None), (0, None, None))
    values: dict[str, int] = {}
    rank_by_encounters(['1', '2', '3'], _min_max(results), values)
    assert values == {'1': 2, '2': 0, '3': 0}


@pytest.mark.unit
def test_art_6_3_alternates_the_cascade_and_the_reapplication():
    """Otto Milvang, "Direct Encounter" (2026), table 8: the seven of table 3
    with 5 and 6 not having met. 2 is placed; 1 and 3 are level on those
    standings, so Art. 6 is reapplied to the other six, where 3 is alone on
    top; on those standings 1 is next, above the 3 that 6 can reach. Among
    4, 5, 6 and 7, 4 is alone on top; 5 and 6, who have not met, can each
    reach 2, and the three left stay level."""
    rows = [list(row) for row in _SEVEN]
    rows[4][5] = rows[5][4] = None
    values: dict[str, int] = {}
    rank_by_encounters(list('1234567'), _min_max(_table(*map(tuple, rows))), values)
    assert values == {'2': 6, '3': 5, '1': 4, '4': 3, '5': 0, '6': 0, '7': 0}
