from unittest import TestCase

import pytest

from data.pairings.round_robin_schedule import (
    REST,
    RoundRobinSchedule,
    ScheduleRound,
    schedule_violations,
)


def _berger(member_count: int, encounters: int = 1, reverse: bool = True):
    return RoundRobinSchedule.berger(
        {number: number for number in range(1, member_count + 1)},
        encounters,
        reverse,
    )


def _violations(
    schedule: RoundRobinSchedule,
    member_count: int,
    encounters: int = 1,
    check_colours: bool = True,
):
    return schedule_violations(
        schedule, range(1, member_count + 1), encounters, str, check_colours
    )


@pytest.mark.unit
class RoundRobinScheduleTestCase(TestCase):
    def test_berger_schedules_keep_the_rules(self):
        for member_count in range(3, 15):
            with self.subTest(member_count=member_count):
                self.assertEqual(_violations(_berger(member_count), member_count), [])
                self.assertEqual(
                    _violations(_berger(member_count, 2), member_count, 2), []
                )

    def test_double_berger_without_reversal_gives_colour_triples(self):
        for member_count in (4, 6, 8):
            with self.subTest(member_count=member_count):
                schedule = _berger(member_count, 2, reverse=False)
                self.assertEqual(
                    _violations(schedule, member_count, 2, check_colours=False), []
                )
                self.assertTrue(_violations(schedule, member_count, 2))

    def test_empty_schedule_reports_unfilled_seats(self):
        schedule = RoundRobinSchedule.empty(5, 1)
        self.assertEqual(len(schedule.rounds), 5)
        violations = _violations(schedule, 5)
        self.assertEqual([violation.round for violation in violations], [1, 2, 3, 4, 5])

    def test_place_moves_a_seated_member_and_empties_their_seat(self):
        schedule = _berger(4)
        round_ = schedule.rounds[1]
        first, second = round_.tables[0]
        third, fourth = round_.tables[1]
        schedule.place(1, (0, 0), third)
        self.assertEqual(round_.tables[0], (third, second))
        self.assertEqual(round_.tables[1], (None, fourth))
        self.assertIsNone(schedule.seat_of(1, first))
        self.assertEqual(schedule.seated(1), {second, third, fourth})

    def test_place_in_the_rest_seat(self):
        schedule = _berger(5)
        resting = schedule.rounds[1].rest
        assert resting is not None
        player = schedule.rounds[1].tables[0][1]
        assert player is not None
        schedule.place(1, (REST, 0), player)
        self.assertEqual(schedule.rounds[1].rest, player)
        self.assertEqual(schedule.rounds[1].tables[0][1], None)
        self.assertIsNone(schedule.seat_of(1, resting))

    def test_swap_colours(self):
        schedule = _berger(4)
        white, black = schedule.rounds[2].tables[1]
        schedule.swap_colours(2, 1)
        self.assertEqual(schedule.rounds[2].tables[1], (black, white))

    def test_repeated_pairing_is_reported_at_its_second_round(self):
        schedule = RoundRobinSchedule(
            {
                1: ScheduleRound([(1, 2), (3, 4)]),
                2: ScheduleRound([(2, 1), (4, 3)]),
                3: ScheduleRound([(1, 4), (2, 3)]),
            }
        )
        violations = _violations(schedule, 4)
        self.assertEqual([violation.round for violation in violations], [2, 2])

    def test_second_rest_is_reported(self):
        schedule = _berger(3)
        schedule.rounds[2] = ScheduleRound(
            [(schedule.rounds[2].rest, schedule.rounds[2].tables[0][0])],
            schedule.rounds[1].rest,
        )
        self.assertIn(2, [violation.round for violation in _violations(schedule, 3)])

    def test_member_seated_twice(self):
        schedule = _berger(4)
        schedule.rounds[1].tables[0] = (1, 1)
        self.assertTrue(
            any(
                'more than once' in violation.message
                for violation in _violations(schedule, 4)
            )
        )

    def test_three_whites_in_a_row(self):
        schedule = RoundRobinSchedule(
            {
                1: ScheduleRound([(1, 2), (3, 4)]),
                2: ScheduleRound([(1, 3), (4, 2)]),
                3: ScheduleRound([(1, 4), (2, 3)]),
            }
        )
        violations = _violations(schedule, 4)
        self.assertEqual([violation.round for violation in violations], [3])
        self.assertEqual(
            violations[0].message, '[1] has White 3 rounds in a row (rounds 1 to 3).'
        )

    def test_a_longer_colour_run_is_reported_once(self):
        schedule = _berger(6)
        # Player 1 gets White from round 1 on once the colours of their games
        # with Black in rounds 1 to 4 are swapped.
        for round_ in (1, 2, 3, 4):
            table, side = schedule.seat_of(round_, 1) or (0, 0)
            if side == 1:
                schedule.swap_colours(round_, table)
        runs = [
            violation
            for violation in _violations(schedule, 6)
            if violation.message.startswith('[1] ')
        ]
        self.assertEqual(len(runs), 1)
        self.assertIn('rounds in a row (rounds 1 to ', runs[0].message)

    def test_a_rest_breaks_a_colour_run(self):
        schedule = RoundRobinSchedule(
            {
                1: ScheduleRound([(1, 2)], 3),
                2: ScheduleRound([(3, 1)], 2),
                3: ScheduleRound([(2, 3)], 1),
            }
        )
        self.assertEqual(_violations(schedule, 3), [])

    def test_same_colours_in_both_games_of_a_double_round_robin(self):
        schedule = _berger(4, 2)
        schedule.swap_colours(6, 0)
        violations = _violations(schedule, 4, 2)
        self.assertIn(
            6,
            [
                violation.round
                for violation in violations
                if 'both games' in violation.message
            ],
        )

    def test_schedule_not_fitting_the_participants(self):
        violations = _violations(_berger(4), 5)
        self.assertEqual(len(violations), 1)
        self.assertIsNone(violations[0].round)

    def test_participant_who_left(self):
        schedule = RoundRobinSchedule.berger({1: 1, 2: 2, 3: 3, 4: 9}, 1, True)
        self.assertTrue(
            any(
                'has left' in violation.message
                for violation in _violations(schedule, 4)
            )
        )

    def test_json_round_trip(self):
        for schedule in (_berger(5, 2), RoundRobinSchedule.empty(6, 1)):
            self.assertEqual(RoundRobinSchedule.from_json(schedule.to_json()), schedule)

    def test_newcomer_to_an_odd_field_plays_the_resting_members(self):
        for member_count in range(3, 16, 2):
            for encounters in (1, 2):
                with self.subTest(member_count=member_count, encounters=encounters):
                    schedule = _berger(member_count, encounters)
                    adapted = schedule.adapted(range(1, member_count + 2))
                    assert adapted is not None
                    self.assertEqual(
                        _violations(adapted, member_count + 1, encounters), []
                    )

    def test_member_leaving_an_even_field_leaves_their_opponents_resting(self):
        for member_count in range(4, 17, 2):
            for encounters in (1, 2):
                with self.subTest(member_count=member_count, encounters=encounters):
                    schedule = _berger(member_count, encounters)
                    adapted = schedule.adapted(range(1, member_count))
                    assert adapted is not None
                    self.assertEqual(
                        _violations(adapted, member_count - 1, encounters), []
                    )

    def test_other_field_changes_cannot_be_adapted(self):
        self.assertIsNone(_berger(4).adapted(range(1, 6)))
        self.assertIsNone(_berger(5).adapted(range(1, 5)))
        self.assertIsNone(_berger(5).adapted(range(1, 8)))
        schedule = _berger(5)
        self.assertIs(schedule.adapted(range(1, 6)), schedule)

    def test_resized_keeps_what_still_fits(self):
        schedule = _berger(4)
        resized = schedule.resized(range(1, 6), 1)
        self.assertEqual(len(resized.rounds), 5)
        for round_ in (1, 2, 3):
            self.assertEqual(
                resized.rounds[round_].tables, schedule.rounds[round_].tables
            )
            self.assertIsNone(resized.rounds[round_].rest)
        for round_ in (4, 5):
            self.assertEqual(resized.rounds[round_].tables, [(None, None)] * 2)

    def test_resized_empties_the_seats_of_members_gone(self):
        schedule = _berger(6)
        resized = schedule.resized(range(1, 5), 1)
        self.assertEqual(len(resized.rounds), 3)
        self.assertTrue(resized.members <= {1, 2, 3, 4})
        for round_ in resized.rounds:
            self.assertEqual(len(resized.rounds[round_].tables), 2)
