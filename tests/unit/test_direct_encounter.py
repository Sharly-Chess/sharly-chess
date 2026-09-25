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
