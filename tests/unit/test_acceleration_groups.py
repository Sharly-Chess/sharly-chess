"""Unit tests for the shifting of the acceleration groups when pairing
numbers are deleted, against a stub tournament."""

from dataclasses import dataclass, field
from typing import Any

import pytest

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
