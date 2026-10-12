"""The Baku acceleration groups across the first pairing.

Before round 1 is paired, group A is the first 2·⌈N/4⌉ players of the
current field (FIDE Handbook C.04.7.1), whatever was stored while the
field was still being entered. From the first pairing on, the stored
limit holds and only late entries move it.

These run against a stub tournament, so no database or pairing engine is
involved.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest

from data.pairings.acceleration import (
    BakuSwissVariation,
    GroupA2GroupsSetting,
    GroupB2GroupsSetting,
)
from data.pairings.settings import ColorSeedSetting
from utils.enum import BoardColor

VARIATION = BakuSwissVariation()
GROUP_A = GroupA2GroupsSetting()
GROUP_B = GroupB2GroupsSetting()


@dataclass
class StubStoredTournament:
    pairing_settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class StubTournament:
    player_count: int
    has_pairings: bool = False
    rounds: int = 9
    pairing_variation: Any = VARIATION
    stored_tournament: StubStoredTournament = field(
        default_factory=StubStoredTournament
    )

    @property
    def stored_pairing_settings(self) -> dict[str, Any]:
        return self.stored_tournament.pairing_settings


def tournament_with_group_a(
    max_a: int, player_count: int, has_pairings: bool = False
) -> Any:
    """A tournament whose group A limit was stored as *max_a*."""
    tournament = StubTournament(player_count=player_count, has_pairings=has_pairings)
    tournament.stored_tournament.pairing_settings |= {
        ColorSeedSetting.static_id(): ColorSeedSetting.to_stored_value(
            BoardColor.WHITE
        ),
        GROUP_A.id: (1, max_a),
        GROUP_B.id: (max_a + 1, player_count),
    }
    return tournament


@pytest.mark.unit
class TestBakuGroupsBeforeTheFirstPairing:
    def test_group_a_follows_the_field(self):
        """Stored for 160 players, read with 162: 2·⌈162/4⌉ = 82."""
        tournament = tournament_with_group_a(80, player_count=162)
        assert GROUP_A.get_value(tournament) == (1, 82)
        assert GROUP_B.get_value(tournament) == (83, 162)

    def test_the_settings_form_shows_the_current_groups(self):
        tournament = tournament_with_group_a(80, player_count=162)
        assert GROUP_A.get_form_data(tournament)[GROUP_A.max_field] == '82'

    def test_a_stale_limit_is_stored_afresh_at_the_first_pairing(self):
        tournament = tournament_with_group_a(80, player_count=162)
        assert not GROUP_A.is_valid(tournament)

    def test_an_added_player_does_not_shift_the_limit(self):
        tournament = tournament_with_group_a(80, player_count=161)
        VARIATION.update_settings_from_added_pairing_number(tournament, 5)
        assert tournament.stored_pairing_settings[GROUP_A.id] == (1, 80)
        assert GROUP_A.get_value(tournament) == (1, 82)


@pytest.mark.unit
class TestBakuGroupsOncePaired:
    def test_the_stored_limit_holds(self):
        """An odd group A, left by a late entry, is kept as stored."""
        tournament = tournament_with_group_a(81, player_count=162, has_pairings=True)
        assert GROUP_A.get_value(tournament) == (1, 81)

    @pytest.mark.parametrize(('pairing_number', 'expected'), [(5, 81), (81, 80)])
    def test_a_late_entry_keeps_the_last_group_a_player(
        self, pairing_number: int, expected: int
    ):
        """Inserted at or above the limit, the late entry joins group A;
        below it, group B."""
        tournament = tournament_with_group_a(80, player_count=161, has_pairings=True)
        VARIATION.update_settings_from_added_pairing_number(tournament, pairing_number)
        assert GROUP_A.get_value(tournament) == (1, expected)
