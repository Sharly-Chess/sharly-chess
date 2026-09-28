import pytest

from data.pairings.knockout import KnockoutPairingSystem, TeamKnockoutPairingSystem
from data.pairings.molter import MolterPairingSystem
from data.pairings.scheveningen import ScheveningenPairingSystem
from data.pairings.systems import SwissPairingSystem, TeamRoundRobinPairingSystem
from data.permissions import PairingAction, RoundStatus, WarningLevel


@pytest.mark.parametrize(
    'pairing_system',
    [
        TeamRoundRobinPairingSystem(),
        ScheveningenPairingSystem(),
        MolterPairingSystem(),
        KnockoutPairingSystem(),
        TeamKnockoutPairingSystem(),
    ],
)
def test_unpairing_does_not_warn_for_regenerable_pairings(
    pairing_system,
):
    allowed_actions = pairing_system.permission_handler.allowed_actions(
        RoundStatus.CURRENT, WarningLevel.NONE, fide_mode=True
    )

    assert PairingAction.FULL_UNPAIRING in allowed_actions


@pytest.mark.parametrize(
    'pairing_system',
    [
        TeamRoundRobinPairingSystem(),
        ScheveningenPairingSystem(),
        MolterPairingSystem(),
    ],
)
def test_a_freed_board_can_be_paired_again_from_the_table(pairing_system):
    allowed_actions = pairing_system.permission_handler.allowed_actions(
        RoundStatus.CURRENT, WarningLevel.NONE, fide_mode=True
    )

    assert PairingAction.MANUAL_UNPAIRING in allowed_actions


@pytest.mark.parametrize(
    'pairing_system',
    [KnockoutPairingSystem(), TeamKnockoutPairingSystem()],
)
@pytest.mark.parametrize(
    'round_status',
    [RoundStatus.PAST, RoundStatus.PREVIOUS, RoundStatus.CURRENT],
)
def test_a_knock_out_board_cannot_be_unpaired_on_its_own(pairing_system, round_status):
    # The bracket says who meets whom, so a freed board has no second answer:
    # it leaves the round a match short and the round is what gets undone.
    existing_actions = pairing_system.permission_handler.existing_actions(round_status)

    assert PairingAction.MANUAL_UNPAIRING not in existing_actions


def test_swiss_unpairing_asks_for_confirmation():
    allowed_actions = SwissPairingSystem().permission_handler.allowed_actions(
        RoundStatus.CURRENT, WarningLevel.NONE, fide_mode=True
    )

    assert PairingAction.FULL_UNPAIRING not in allowed_actions
    assert PairingAction.MANUAL_UNPAIRING not in allowed_actions
