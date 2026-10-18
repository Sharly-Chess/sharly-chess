"""Unit tests for the shifting of the acceleration groups when pairing
numbers are deleted, against a stub tournament."""

from dataclasses import dataclass, field
from typing import Any

import pytest

from data.pairing_numbers import PairingNumbers
from data.pairings.acceleration import (
    BakuSwissVariation,
    ProgressiveSwissVariation,
)


@dataclass
class StubStoredTournament:
    pairing_settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class StubTournament:
    player_count: int
    stored_tournament: StubStoredTournament
    pairing_variation: Any = None

    @property
    def stored_pairing_settings(self) -> dict[str, Any]:
        return self.stored_tournament.pairing_settings


def stub_tournament(player_count: int, pairing_settings: dict[str, Any]) -> Any:
    return StubTournament(player_count, StubStoredTournament(dict(pairing_settings)))


@pytest.mark.unit
class TestDeletedPairingNumbers:
    def test_three_groups_follow_the_players_left_in_the_field(self):
        tournament = stub_tournament(
            85, {'GROUP_A_3': [1, 32], 'GROUP_B_3': [33, 63], 'GROUP_C_3': [64, 89]}
        )
        assert ProgressiveSwissVariation().update_settings_from_deleted_pairing_numbers(
            tournament, [5, 20, 40, 70]
        )
        assert tournament.stored_pairing_settings == {
            'GROUP_A_3': (1, 30),
            'GROUP_B_3': (31, 60),
            'GROUP_C_3': (61, 85),
        }

    def test_last_number_deleted_shrinks_the_last_group(self):
        tournament = stub_tournament(
            87, {'GROUP_A_3': [1, 29], 'GROUP_B_3': [30, 59], 'GROUP_C_3': [60, 88]}
        )
        assert ProgressiveSwissVariation().update_settings_from_deleted_pairing_numbers(
            tournament, []
        )
        assert tournament.stored_pairing_settings == {
            'GROUP_A_3': (1, 29),
            'GROUP_B_3': (30, 59),
            'GROUP_C_3': (60, 87),
        }

    def test_two_groups_follow_the_players_left_in_the_field(self):
        tournament = stub_tournament(78, {'GROUP_A_2': [1, 40], 'GROUP_B_2': [41, 80]})
        assert BakuSwissVariation().update_settings_from_deleted_pairing_numbers(
            tournament, [10, 50]
        )
        assert tournament.stored_pairing_settings == {
            'GROUP_A_2': (1, 39),
            'GROUP_B_2': (40, 78),
        }

    def test_nothing_to_shift_without_groups(self):
        tournament = stub_tournament(78, {})
        assert not BakuSwissVariation().update_settings_from_deleted_pairing_numbers(
            tournament, [10]
        )
        assert not ProgressiveSwissVariation().update_settings_from_deleted_pairing_numbers(
            tournament, [10]
        )


@dataclass
class StubPlayer:
    pairing_number: int


def stub_player(pairing_number: int) -> Any:
    return StubPlayer(pairing_number)


def moved(
    pairing_settings: dict[str, Any], former_numbers_in_new_order: list[int]
) -> dict[str, Any]:
    """The settings once the players, numbered 1 to n, have been re-sorted
    so that the player formerly numbered ``former_numbers_in_new_order[i]``
    now holds number ``i + 1``."""
    tournament = stub_tournament(len(former_numbers_in_new_order), pairing_settings)
    tournament.pairing_variation = ProgressiveSwissVariation()
    PairingNumbers(tournament)._update_settings_from_moved_players(
        [stub_player(number) for number in former_numbers_in_new_order]
    )
    return {
        key: tuple(value) for key, value in tournament.stored_pairing_settings.items()
    }


GROUPS = {'GROUP_A_3': (1, 4), 'GROUP_B_3': (5, 8), 'GROUP_C_3': (9, 12)}


@pytest.mark.unit
class TestMovedPlayers:
    def test_player_moved_into_a_higher_group_joins_it(self):
        assert moved(GROUPS, [1, 2, 7, 3, 4, 5, 6, 8, 9, 10, 11, 12]) == {
            'GROUP_A_3': (1, 5),
            'GROUP_B_3': (6, 8),
            'GROUP_C_3': (9, 12),
        }

    def test_player_moved_into_a_lower_group_joins_it(self):
        assert moved(GROUPS, [1, 3, 4, 5, 6, 7, 8, 9, 10, 2, 11, 12]) == {
            'GROUP_A_3': (1, 3),
            'GROUP_B_3': (4, 7),
            'GROUP_C_3': (8, 12),
        }

    def test_player_moved_within_a_group_changes_nothing(self):
        settings = moved(GROUPS, [1, 2, 3, 4, 7, 5, 6, 8, 9, 10, 11, 12])
        assert settings == GROUPS

    def test_unchanged_order_changes_nothing(self):
        assert moved(GROUPS, list(range(1, 13))) == GROUPS

    @pytest.mark.parametrize(
        ('values', 'expected_length'),
        [([], 0), ([1, 2, 3], 3), ([3, 2, 1], 1), ([1, 5, 2, 3, 4], 4)],
    )
    def test_longest_increasing_run(self, values: list[int], expected_length: int):
        indexes = sorted(PairingNumbers._longest_increasing_run(values))
        assert len(indexes) == expected_length
        run = [values[index] for index in indexes]
        assert run == sorted(set(run))
