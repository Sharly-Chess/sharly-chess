"""Unit tests for the arbiter-defined accelerated systems, both of which
compile to TRF26 250 records: the custom one (rules over ranges of
pairing numbers) and the initial-score one (a value per player).

These exercise the settings (form / storage round-trips and validation)
and the variations (virtual points, pairing-number shifts) against a stub
tournament, so no database or pairing engine is involved.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pytest

from plugins.pairing_acceleration.pairing_settings import (
    AccelerationRule,
    CustomAccelerationSetting,
    InitialPairingScoreSetting,
)
from plugins.pairing_acceleration.pairing_variations import (
    CustomAccelerationSwissVariation,
    InitialScoreSwissVariation,
)

SETTING = CustomAccelerationSetting()
VARIATION = CustomAccelerationSwissVariation()
SCORE_SETTING = InitialPairingScoreSetting()
SCORE_VARIATION = InitialScoreSwissVariation()

# Two players carrying a score over from an earlier tournament.
SCORES = {11: 6.5, 12: 4.0}

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
    tournament_players: list[Any] = field(default_factory=list)
    event: Any = None
    stored_tournament: StubStoredTournament = field(
        default_factory=StubStoredTournament
    )

    @property
    def stored_pairing_settings(self) -> dict[str, Any]:
        return self.stored_tournament.pairing_settings


@dataclass
class StubPlayer:
    pairing_number: int | None
    id: int = 0
    stored_player: Any = None


def stub_tournament(**kwargs) -> Any:
    """Typed as Any: the stub carries only the handful of attributes these
    units read, not the whole Tournament surface."""
    return StubTournament(**kwargs)


def stub_player(pairing_number: int | None, **kwargs) -> Any:
    return StubPlayer(pairing_number, **kwargs)


def stored_rules(tournament: Any) -> list[AccelerationRule]:
    rules = VARIATION._stored_rules(tournament)
    assert rules is not None
    return rules


def tournament_with(rules: list[AccelerationRule], **kwargs) -> Any:
    tournament = StubTournament(**kwargs)
    tournament.stored_tournament.pairing_settings[SETTING.id] = (
        CustomAccelerationSetting.to_stored_value(rules)
    )
    return tournament


def tournament_with_scores(scores: dict[int, float], **kwargs) -> Any:
    tournament = StubTournament(**kwargs)
    tournament.stored_tournament.pairing_settings[SCORE_SETTING.id] = (
        InitialPairingScoreSetting.to_stored_value(scores)
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
        assert SETTING.get_data_errors(stub_tournament(), form_data()) == {}

    def test_round_out_of_range(self):
        data = form_data(**{SETTING.field(0, 'last_round'): '12'})
        errors = SETTING.get_data_errors(stub_tournament(rounds=9), data)
        assert SETTING.field(0, 'last_round') in errors

    def test_pairing_number_out_of_range(self):
        data = form_data(**{SETTING.field(0, 'last_number'): '999'})
        errors = SETTING.get_data_errors(stub_tournament(player_count=80), data)
        assert SETTING.field(0, 'last_number') in errors

    def test_inverted_range(self):
        data = form_data(
            **{
                SETTING.field(0, 'first_round'): '5',
                SETTING.field(0, 'last_round'): '2',
            }
        )
        errors = SETTING.get_data_errors(stub_tournament(), data)
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
        errors = SETTING.get_data_errors(stub_tournament(), data)
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
        assert SETTING.get_data_errors(stub_tournament(), data) == {}

    @pytest.mark.parametrize('vpoints', ['-1', '100', 'abc', ''])
    def test_rejected_vpoints(self, vpoints: str):
        data = form_data(**{SETTING.field(0, 'vpoints'): vpoints})
        errors = SETTING.get_data_errors(stub_tournament(), data)
        assert SETTING.field(0, 'vpoints') in errors

    def test_vpoints_limited_to_one_decimal(self):
        # The TRF26 250 points field only holds one decimal.
        data = form_data(**{SETTING.field(0, 'vpoints'): '1.25'})
        errors = SETTING.get_data_errors(stub_tournament(), data)
        assert SETTING.field(0, 'vpoints') in errors

    def test_check_value_accepts_valid_rules(self):
        assert CustomAccelerationSetting.check_value(stub_tournament(), RULES)

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
        assert not CustomAccelerationSetting.check_value(stub_tournament(), [rule])

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
        player = stub_player(pairing_number=pairing_number)
        assert (
            VARIATION.compute_virtual_points(tournament, player, at_round) == expected
        )

    def test_no_virtual_points_without_a_pairing_number(self):
        tournament = tournament_with(RULES)
        player = stub_player(pairing_number=None)
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
        assert [rule.number_range for rule in stored_rules(tournament)] == [
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
        assert stored_rules(tournament)[0].number_range == (10, 20)

    def test_deleted_pairing_number_inside_the_rule(self):
        tournament = tournament_with(
            [AccelerationRule(1.0, 1, 3, number_range=(10, 20))], player_count=79
        )
        assert VARIATION.update_settings_from_deleted_pairing_numbers(tournament, [15])
        assert stored_rules(tournament)[0].number_range == (10, 19)

    def test_emptied_rule_is_dropped(self):
        tournament = tournament_with(
            [AccelerationRule(1.0, 1, 3, number_range=(10, 10))], player_count=79
        )
        assert VARIATION.update_settings_from_deleted_pairing_numbers(tournament, [10])
        assert stored_rules(tournament) == []

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
        assert stored_rules(tournament)[0].number_range == expected

    def test_nothing_to_shift_without_rules(self):
        tournament = stub_tournament()
        assert not VARIATION.update_settings_from_deleted_pairing_numbers(
            tournament, [1]
        )
        assert not VARIATION.update_settings_from_added_pairing_number(tournament, 1)


@pytest.mark.unit
class TestInitialPairingScoreSetting:
    def test_storage_round_trip(self):
        stored = InitialPairingScoreSetting.to_stored_value(SCORES)
        assert stored == {'11': 6.5, '12': 4.0}
        assert InitialPairingScoreSetting.from_stored_value(stored) == SCORES

    def test_form_round_trip(self):
        data = SCORE_SETTING.to_form_data(SCORES)
        assert data == {
            SCORE_SETTING.player_field(11): '6.5',
            SCORE_SETTING.player_field(12): '4',
        }
        assert SCORE_SETTING.from_form_data(data) == SCORES

    def test_blank_and_zero_scores_are_dropped(self):
        data = {
            SCORE_SETTING.player_field(11): '6.5',
            SCORE_SETTING.player_field(12): '',
            SCORE_SETTING.player_field(13): '0',
        }
        assert SCORE_SETTING.from_form_data(data) == {11: 6.5}

    def test_other_fields_are_ignored(self):
        # The modal posts every setting of the variation at once.
        data = {
            SCORE_SETTING.player_field(11): '6.5',
            'COLOR_SEED': 'W',
            f'{SCORE_SETTING.player_field_base}abc': '3',
        }
        assert SCORE_SETTING.from_form_data(data) == {11: 6.5}

    @pytest.mark.parametrize('score', ['-1', '100', 'abc'])
    def test_rejected_scores(self, score: str):
        data = {SCORE_SETTING.player_field(11): score}
        assert SCORE_SETTING.player_field(11) in SCORE_SETTING.get_data_errors(
            stub_tournament(), data
        )

    def test_score_limited_to_one_decimal(self):
        data = {SCORE_SETTING.player_field(11): '6.25'}
        assert SCORE_SETTING.player_field(11) in SCORE_SETTING.get_data_errors(
            stub_tournament(), data
        )

    def test_blank_score_is_not_an_error(self):
        data = {SCORE_SETTING.player_field(11): ''}
        assert SCORE_SETTING.get_data_errors(stub_tournament(), data) == {}

    def test_scores_of_departed_players_do_not_invalidate_the_setting(self):
        # Player 99 has left the tournament; the arbiter's other values
        # must survive rather than being reset to nothing.
        tournament = stub_tournament()
        tournament.stored_tournament.pairing_settings[SCORE_SETTING.id] = (
            InitialPairingScoreSetting.to_stored_value(SCORES | {99: 1.0})
        )
        assert InitialPairingScoreSetting.get_value(tournament) == SCORES | {99: 1.0}


@pytest.mark.unit
class TestInitialScoreVariation:
    def test_virtual_points_apply_to_every_round(self):
        tournament = tournament_with_scores(SCORES)
        player = stub_player(pairing_number=1, id=11)
        assert SCORE_VARIATION.compute_virtual_points(tournament, player, 1) == 6.5
        assert SCORE_VARIATION.compute_virtual_points(tournament, player, 9) == 6.5

    def test_no_virtual_points_without_a_score(self):
        tournament = tournament_with_scores(SCORES)
        player = stub_player(pairing_number=3, id=13)
        assert SCORE_VARIATION.compute_virtual_points(tournament, player, 1) == 0.0

    def test_print_real_points(self):
        assert SCORE_VARIATION.print_real_points(tournament_with_scores(SCORES), 1)
        assert not SCORE_VARIATION.print_real_points(tournament_with_scores({}), 1)

    def test_one_trf_rule_per_scored_player(self):
        tournament = tournament_with_scores(SCORES)
        tournament.tournament_players = [
            stub_player(pairing_number=2, id=12),
            stub_player(pairing_number=1, id=11),
            stub_player(pairing_number=3, id=13),  # no score → no record
        ]
        assert SCORE_VARIATION.get_tournament_accelerated_rules(tournament) == [
            AccelerationRule(6.5, 1, 9, number_range=(1, 1)),
            AccelerationRule(4.0, 1, 9, number_range=(2, 2)),
        ]

    def test_players_without_a_pairing_number_are_skipped(self):
        tournament = tournament_with_scores(SCORES)
        tournament.tournament_players = [stub_player(pairing_number=None, id=11)]
        assert SCORE_VARIATION.get_tournament_accelerated_rules(tournament) == []


@dataclass
class StubStoredPlayer:
    id: int
    last_name: str = ''
    first_name: str | None = None
    date_of_birth: Any = None
    fide_id: int | None = None
    plugin_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class StubSourcePlayer:
    id: int
    stored_player: StubStoredPlayer
    score: float

    def points_total(self) -> float:
        return self.score


@dataclass
class StubEvent:
    uniq_id: str
    tournaments_by_id: dict[int, Any] = field(default_factory=dict)

    def get_player_identity_keys(self, stored_player: StubStoredPlayer) -> set[object]:
        # Same shape as Event.get_player_identity_keys, without the plugins.
        keys: set[object] = set()
        if stored_player.date_of_birth and stored_player.first_name:
            keys.add(
                (
                    'name',
                    stored_player.last_name,
                    stored_player.first_name,
                    stored_player.date_of_birth,
                )
            )
        if stored_player.fide_id:
            keys.add(('fide', stored_player.fide_id))
        return keys


def make_fill_case() -> tuple[Any, dict[str, str]]:
    """A tournament whose three players are, in an earlier tournament of
    the same event, three *different* player records — matched by FIDE ID
    for two of them and by name + birth date for the third."""
    birth = date(2001, 2, 3)
    target_players = [
        stub_player(pairing_number=1, id=11),
        stub_player(pairing_number=2, id=12),
        stub_player(pairing_number=3, id=13),
    ]
    target_players[0].stored_player = StubStoredPlayer(id=11, fide_id=500)
    target_players[1].stored_player = StubStoredPlayer(
        id=12, last_name='MARTIN', first_name='Jean', date_of_birth=birth
    )
    target_players[2].stored_player = StubStoredPlayer(id=13, fide_id=502)

    source = stub_tournament()
    source.tournament_players = [
        # Different ids from the target players on purpose.
        StubSourcePlayer(91, StubStoredPlayer(id=91, fide_id=500), 6.5),
        StubSourcePlayer(
            92,
            StubStoredPlayer(
                id=92, last_name='MARTIN', first_name='Jean', date_of_birth=birth
            ),
            4.0,
        ),
    ]

    tournament = stub_tournament(tournament_players=target_players)
    tournament.event = StubEvent(uniq_id='ev', tournaments_by_id={7: source})
    data = {
        SCORE_SETTING.source_event_field: 'ev',
        SCORE_SETTING.source_tournament_field: '7',
        SCORE_SETTING.coefficient_field: '1',
        SCORE_SETTING.action_field: SCORE_SETTING.ACTION_FILL,
    }
    return tournament, data


@pytest.mark.unit
class TestInitialScoreFill:
    def test_players_are_matched_by_identity_not_by_id(self):
        tournament, data = make_fill_case()
        filled = SCORE_SETTING.apply_action(tournament, data)
        assert filled[SCORE_SETTING.player_field(11)] == '6.5'
        assert filled[SCORE_SETTING.player_field(12)] == '4'
        # No counterpart in the source tournament.
        assert filled[SCORE_SETTING.player_field(13)] == ''
        assert SCORE_SETTING.from_form_data(filled) == {11: 6.5, 12: 4.0}

    def test_coefficient_is_applied_and_rounded_to_one_decimal(self):
        tournament, data = make_fill_case()
        filled = SCORE_SETTING.apply_action(
            tournament, data | {SCORE_SETTING.coefficient_field: '0.5'}
        )
        assert filled[SCORE_SETTING.player_field(11)] == '3.3'  # 6.5 × 0.5 = 3.25
        assert filled[SCORE_SETTING.player_field(12)] == '2'

    def test_add_mode_accumulates_and_keeps_unmatched_values(self):
        tournament, data = make_fill_case()
        filled = SCORE_SETTING.apply_action(
            tournament,
            data
            | {
                SCORE_SETTING.mode_field: 'add',
                SCORE_SETTING.player_field(11): '1',
                SCORE_SETTING.player_field(13): '2',
            },
        )
        assert filled[SCORE_SETTING.player_field(11)] == '7.5'
        # Untouched: adding must not wipe a hand-entered value.
        assert filled[SCORE_SETTING.player_field(13)] == '2'

    def test_replace_mode_clears_unmatched_values(self):
        tournament, data = make_fill_case()
        filled = SCORE_SETTING.apply_action(
            tournament, data | {SCORE_SETTING.player_field(13): '2'}
        )
        assert filled[SCORE_SETTING.player_field(13)] == ''

    def test_report_counts_matched_and_missing_players(self):
        tournament, data = make_fill_case()
        filled = SCORE_SETTING.apply_action(tournament, data)
        assert '2' in filled[SCORE_SETTING.report_field]
        assert '1' in filled[SCORE_SETTING.report_field]

    def test_no_action_leaves_the_data_untouched(self):
        tournament, data = make_fill_case()
        del data[SCORE_SETTING.action_field]
        assert SCORE_SETTING.apply_action(tournament, data) == data

    def test_unknown_source_tournament_changes_nothing(self):
        tournament, data = make_fill_case()
        filled = SCORE_SETTING.apply_action(
            tournament, data | {SCORE_SETTING.source_tournament_field: '999'}
        )
        assert SCORE_SETTING.from_form_data(filled) == {}


@pytest.mark.unit
class TestCommaDecimals:
    """The form helpers accept a comma as the decimal separator, which
    French arbiters type. Validation and reading must agree on it."""

    def test_custom_rule_accepts_a_comma(self):
        data = form_data(**{SETTING.field(0, 'vpoints'): '1,5'})
        assert SETTING.get_data_errors(stub_tournament(), data) == {}
        assert SETTING.from_form_data(data)[0].vpoints == 1.5

    def test_initial_score_accepts_a_comma(self):
        data = {SCORE_SETTING.player_field(11): '6,5'}
        assert SCORE_SETTING.get_data_errors(stub_tournament(), data) == {}
        assert SCORE_SETTING.from_form_data(data) == {11: 6.5}


# A rule left open at both ends: every round, every player.
OPEN_RULE = AccelerationRule(
    vpoints=1.0,
    first_round=None,
    last_round=None,
    number_range=(None, None),
)


@pytest.mark.unit
class TestOpenEndedRules:
    """A bound left empty means "from the start" / "to the end", and is
    resolved against the tournament each time the rule is read — so the
    rule keeps covering the whole field as rounds and players arrive."""

    def test_empty_bounds_survive_the_round_trips(self):
        stored = CustomAccelerationSetting.to_stored_value([OPEN_RULE])
        assert stored[0]['first_round'] is None
        assert stored[0]['last_number'] is None
        assert CustomAccelerationSetting.from_stored_value(stored) == [OPEN_RULE]
        data = SETTING.to_form_data([OPEN_RULE])
        assert data[SETTING.field(0, 'first_round')] == ''
        assert data[SETTING.field(0, 'last_number')] == ''
        assert SETTING.from_form_data(data) == [OPEN_RULE]

    def test_an_empty_bound_is_accepted_by_the_form(self):
        data = SETTING.to_form_data([OPEN_RULE])
        assert SETTING.get_data_errors(stub_tournament(), data) == {}

    def test_the_bounds_resolve_to_the_tournament(self):
        tournament = stub_tournament(rounds=9, player_count=80)
        assert OPEN_RULE.resolved_round_range(tournament) == (1, 9)
        assert OPEN_RULE.resolved_number_range(tournament) == (1, 80)

    def test_the_bounds_follow_the_tournament_rather_than_being_pinned(self):
        # The same rule, read against a bigger field, covers the newcomers.
        bigger = stub_tournament(rounds=11, player_count=100)
        assert OPEN_RULE.resolved_round_range(bigger) == (1, 11)
        assert OPEN_RULE.resolved_number_range(bigger) == (1, 100)

    def test_only_one_end_may_be_left_open(self):
        rule = AccelerationRule(
            vpoints=0.5, first_round=3, last_round=None, number_range=(10, None)
        )
        tournament = stub_tournament(rounds=9, player_count=80)
        assert rule.resolved_round_range(tournament) == (3, 9)
        assert rule.resolved_number_range(tournament) == (10, 80)

    def test_two_open_ended_rules_still_collide(self):
        # Overlaps are judged on the resolved ranges, so "to the end"
        # twice is caught even though nothing was typed.
        data = SETTING.to_form_data([OPEN_RULE, OPEN_RULE])
        errors = SETTING.get_data_errors(stub_tournament(), data)
        assert errors

    def test_an_open_rule_accelerates_every_player_and_round(self):
        tournament = tournament_with([OPEN_RULE], rounds=5, player_count=40)
        for pairing_number in (1, 20, 40):
            for round_ in (1, 3, 5):
                assert (
                    VARIATION.compute_virtual_points(
                        tournament, stub_player(pairing_number), at_round=round_
                    )
                    == 1.0
                )

    def test_adding_a_player_leaves_an_open_bound_alone(self):
        # A concrete bound is shifted to keep covering the same players;
        # an empty one has nothing to shift.
        tournament = tournament_with([OPEN_RULE], player_count=41)
        VARIATION.update_settings_from_added_pairing_number(tournament, 1)
        assert stored_rules(tournament)[0].number_range == (None, None)


@pytest.mark.unit
class TestPairingNumberAttribution:
    """Rules address pairing numbers, so they shift when a player is
    inserted into an already-numbered field — but not when the numbers
    are first handed out, which is what happens at the first pairing."""

    def test_a_rule_is_shifted_when_a_player_joins_a_numbered_field(self):
        rule = AccelerationRule(
            vpoints=1.0, first_round=1, last_round=3, number_range=(1, 2)
        )
        tournament = tournament_with([rule], player_count=9)
        # A player takes number 1, pushing the two accelerated players down.
        VARIATION.update_settings_from_added_pairing_number(tournament, 1)
        assert stored_rules(tournament)[0].number_range == (2, 3)

    def test_the_first_numbering_does_not_shift_a_rule(self):
        """Repeating the shift once per player — which is what the first
        pairing used to do — marched a rule for numbers 1-2 off the end
        of the field, accelerating nobody."""
        rule = AccelerationRule(
            vpoints=1.0, first_round=1, last_round=3, number_range=(1, 2)
        )
        tournament = tournament_with([rule], rounds=5, player_count=8)
        for index in range(8):
            VARIATION.update_settings_from_added_pairing_number(tournament, index + 1)
        # The guard now lives in Tournament._set_tournament_players_
        # pairing_numbers; this records what it protects against.
        assert stored_rules(tournament)[0].number_range == (9, 10)
        assert not [
            number
            for number in range(1, 9)
            if VARIATION.compute_virtual_points(
                tournament, stub_player(number), at_round=1
            )
        ]
