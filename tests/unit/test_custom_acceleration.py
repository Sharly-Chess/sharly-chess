"""Unit tests for the custom accelerated system (TRF26 250 records).

These exercise the setting (form / storage round-trips and validation)
and the variation (virtual points, pairing-number shifts) against a stub
tournament, so no database or pairing engine is involved.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest

from plugins.pairing_acceleration.pairing_settings import (
    AccelerationRule,
    CustomAccelerationSetting,
)
from plugins.pairing_acceleration.pairing_variations import (
    CustomAccelerationSwissVariation,
)

SETTING = CustomAccelerationSetting()
VARIATION = CustomAccelerationSwissVariation()

# Group A (numbers 1-40) is given a full point over the first three
# rounds, then half a point in round 4.
RULES = [
    AccelerationRule(vpoints=1.0, first_round=1, last_round=3, number_range=(1, 40)),
    AccelerationRule(vpoints=0.5, first_round=4, last_round=4, number_range=(1, 40)),
]


@dataclass
class StubStoredTournament:
    pairing_settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class StubTournament:
    rounds: int = 9
    player_count: int = 80
    stored_tournament: StubStoredTournament = field(
        default_factory=StubStoredTournament
    )

    @property
    def stored_pairing_settings(self) -> dict[str, Any]:
        return self.stored_tournament.pairing_settings


@dataclass
class StubPlayer:
    pairing_number: int | None


def tournament_with(rules: list[AccelerationRule], **kwargs) -> StubTournament:
    tournament = StubTournament(**kwargs)
    tournament.stored_tournament.pairing_settings[SETTING.id] = (
        CustomAccelerationSetting.to_stored_value(rules)
    )
    return tournament


def form_data(**overrides: str) -> dict[str, str]:
    data = SETTING.to_form_data(RULES)
    data.update(overrides)
    return data


@pytest.mark.unit
class TestCustomAccelerationSetting:
    def test_storage_round_trip(self):
        stored = CustomAccelerationSetting.to_stored_value(RULES)
        assert CustomAccelerationSetting.from_stored_value(stored) == RULES

    def test_form_round_trip(self):
        data = SETTING.to_form_data(RULES)
        assert SETTING.row_indexes(data) == [0, 1]
        assert SETTING.from_form_data(data) == RULES

    def test_row_indexes_need_not_be_contiguous(self):
        # A row deleted client-side leaves a hole in the numbering; the
        # remaining rows must still be read.
        data = {
            key.replace('_1_', '_7_'): value
            for key, value in SETTING.to_form_data(RULES).items()
        }
        assert SETTING.row_indexes(data) == [0, 7]
        assert SETTING.from_form_data(data) == RULES

    def test_valid_rules_have_no_errors(self):
        assert SETTING.get_data_errors(StubTournament(), form_data()) == {}

    def test_round_out_of_range(self):
        data = form_data(**{SETTING.field(0, 'last_round'): '12'})
        errors = SETTING.get_data_errors(StubTournament(rounds=9), data)
        assert SETTING.field(0, 'last_round') in errors

    def test_pairing_number_out_of_range(self):
        data = form_data(**{SETTING.field(0, 'last_number'): '999'})
        errors = SETTING.get_data_errors(StubTournament(player_count=80), data)
        assert SETTING.field(0, 'last_number') in errors

    def test_inverted_range(self):
        data = form_data(
            **{
                SETTING.field(0, 'first_round'): '5',
                SETTING.field(0, 'last_round'): '2',
            }
        )
        errors = SETTING.get_data_errors(StubTournament(), data)
        assert SETTING.field(0, 'last_round') in errors

    def test_overlapping_rules(self):
        # Round 2 of numbers 30-40 is already accelerated by the first rule.
        data = form_data(
            **{
                SETTING.field(2, 'vpoints'): '1',
                SETTING.field(2, 'first_round'): '2',
                SETTING.field(2, 'last_round'): '2',
                SETTING.field(2, 'first_number'): '30',
                SETTING.field(2, 'last_number'): '50',
            }
        )
        errors = SETTING.get_data_errors(StubTournament(), data)
        assert SETTING.field(2, 'first_number') in errors

    def test_adjacent_rules_do_not_overlap(self):
        # Same numbers but disjoint rounds, and same rounds but disjoint
        # numbers: neither is an overlap.
        data = form_data(
            **{
                SETTING.field(2, 'vpoints'): '1',
                SETTING.field(2, 'first_round'): '1',
                SETTING.field(2, 'last_round'): '3',
                SETTING.field(2, 'first_number'): '41',
                SETTING.field(2, 'last_number'): '80',
            }
        )
        assert SETTING.get_data_errors(StubTournament(), data) == {}

    @pytest.mark.parametrize('vpoints', ['-1', '100', 'abc', ''])
    def test_rejected_vpoints(self, vpoints: str):
        data = form_data(**{SETTING.field(0, 'vpoints'): vpoints})
        errors = SETTING.get_data_errors(StubTournament(), data)
        assert SETTING.field(0, 'vpoints') in errors

    def test_vpoints_limited_to_one_decimal(self):
        # The TRF26 250 points field only holds one decimal.
        data = form_data(**{SETTING.field(0, 'vpoints'): '1.25'})
        errors = SETTING.get_data_errors(StubTournament(), data)
        assert SETTING.field(0, 'vpoints') in errors

    def test_check_value_accepts_valid_rules(self):
        assert CustomAccelerationSetting.check_value(StubTournament(), RULES)

    @pytest.mark.parametrize(
        'rule',
        [
            AccelerationRule(1.0, 1, 99, number_range=(1, 2)),
            AccelerationRule(1.0, 1, 2, number_range=(1, 999)),
            AccelerationRule(1.0, 3, 1, number_range=(1, 2)),
            AccelerationRule(1.0, 1, 2, number_range=(9, 2)),
            AccelerationRule(1.0, 1, 2),
        ],
    )
    def test_check_value_rejects_broken_rules(self, rule: AccelerationRule):
        assert not CustomAccelerationSetting.check_value(StubTournament(), [rule])

    def test_get_value_falls_back_when_stored_rules_do_not_fit(self):
        # A tournament shrunk below the stored ranges must not silently
        # accelerate the wrong players.
        tournament = tournament_with(RULES, player_count=20)
        assert CustomAccelerationSetting.get_value(tournament) == []


@pytest.mark.unit
class TestCustomAccelerationVariation:
    def test_exports_its_rules_to_the_trf(self):
        tournament = tournament_with(RULES)
        assert VARIATION.include_accelerated_rules_in_trf
        assert VARIATION.get_tournament_accelerated_rules(tournament) == RULES

    @pytest.mark.parametrize(
        ('pairing_number', 'at_round', 'expected'),
        [
            (1, 1, 1.0),
            (40, 3, 1.0),
            (40, 4, 0.5),
            (41, 1, 0.0),  # outside the accelerated numbers
            (1, 5, 0.0),  # after the accelerated rounds
        ],
    )
    def test_virtual_points(self, pairing_number: int, at_round: int, expected: float):
        tournament = tournament_with(RULES)
        player = StubPlayer(pairing_number=pairing_number)
        assert (
            VARIATION.compute_virtual_points(tournament, player, at_round) == expected
        )

    def test_no_virtual_points_without_a_pairing_number(self):
        tournament = tournament_with(RULES)
        player = StubPlayer(pairing_number=None)
        assert VARIATION.compute_virtual_points(tournament, player, 1) == 0.0

    @pytest.mark.parametrize(
        ('current_round', 'expected'), [(1, True), (4, True), (5, False)]
    )
    def test_print_real_points_while_accelerating(
        self, current_round: int, expected: bool
    ):
        tournament = tournament_with(RULES)
        assert VARIATION.print_real_points(tournament, current_round) is expected

    def test_deleted_pairing_number_shifts_the_rules(self):
        # Deleting #5 moves everyone above it down one, so the rule has to
        # follow to keep accelerating the same players.
        tournament = tournament_with(RULES, player_count=79)
        assert VARIATION.update_settings_from_deleted_pairing_numbers(tournament, [5])
        assert [rule.number_range for rule in VARIATION._stored_rules(tournament)] == [
            (1, 39),
            (1, 39),
        ]

    def test_deleted_pairing_number_above_the_rule_is_ignored(self):
        tournament = tournament_with(
            [AccelerationRule(1.0, 1, 3, number_range=(10, 20))], player_count=79
        )
        assert not VARIATION.update_settings_from_deleted_pairing_numbers(
            tournament, [50]
        )
        assert VARIATION._stored_rules(tournament)[0].number_range == (10, 20)

    def test_deleted_pairing_number_inside_the_rule(self):
        tournament = tournament_with(
            [AccelerationRule(1.0, 1, 3, number_range=(10, 20))], player_count=79
        )
        assert VARIATION.update_settings_from_deleted_pairing_numbers(tournament, [15])
        assert VARIATION._stored_rules(tournament)[0].number_range == (10, 19)

    def test_emptied_rule_is_dropped(self):
        tournament = tournament_with(
            [AccelerationRule(1.0, 1, 3, number_range=(10, 10))], player_count=79
        )
        assert VARIATION.update_settings_from_deleted_pairing_numbers(tournament, [10])
        assert VARIATION._stored_rules(tournament) == []

    @pytest.mark.parametrize(
        ('added', 'expected'),
        [
            (5, (11, 21)),  # inserted below the rule → the whole rule moves up
            (15, (10, 21)),  # inserted inside it → the rule grows
            (25, (10, 20)),  # inserted above it → unchanged
        ],
    )
    def test_added_pairing_number_shifts_the_rules(
        self, added: int, expected: tuple[int, int]
    ):
        tournament = tournament_with(
            [AccelerationRule(1.0, 1, 3, number_range=(10, 20))], player_count=81
        )
        VARIATION.update_settings_from_added_pairing_number(tournament, added)
        assert VARIATION._stored_rules(tournament)[0].number_range == expected

    def test_nothing_to_shift_without_rules(self):
        tournament = StubTournament()
        assert not VARIATION.update_settings_from_deleted_pairing_numbers(
            tournament, [1]
        )
        assert not VARIATION.update_settings_from_added_pairing_number(tournament, 1)
