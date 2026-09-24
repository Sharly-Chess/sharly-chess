"""The random tournament generator.

The check-list requires one (C.04.A Annex 3, question 19), lists what it
must let the user vary (question 24), asks that it not answer the same
twice unless asked to (question 30), and that what it writes have
"correct pairings and standings" (question 31).
"""

import collections
from pathlib import Path

import pytest

from data.pairings.random_tournaments import (
    Frequency,
    TournamentSettings,
    generate_tournament_file,
)


def _result_codes(trf_path: Path) -> collections.Counter:
    """Every round's result letter, over all players."""
    codes: collections.Counter = collections.Counter()
    for line in trf_path.read_text(encoding='ascii').splitlines():
        if not line.startswith('001'):
            continue
        for start in range(91, len(line), 10):
            field = line[start : start + 8]
            if len(field) == 8:
                codes[field[7]] += 1
    return codes


@pytest.mark.unit
@pytest.mark.parametrize(
    ('written', 'expected'),
    [
        ('4', Frequency(count=4)),
        ('5%', Frequency(rate=0.05)),
        ('0.05', Frequency(rate=0.05)),
        ('0', Frequency(count=0)),
        (None, None),
    ],
)
def test_a_frequency_is_a_number_or_a_percentage(written, expected):
    assert Frequency.parse(written) == expected


@pytest.mark.unit
def test_a_fixed_number_of_byes_is_the_number_written(tmp_path: Path):
    """Question 24 asks for each kind to be settable as a fixed number."""
    trf_path = tmp_path / 'counted.trf'
    generate_tournament_file(
        TournamentSettings(
            players=30,
            rounds=9,
            half_point_byes=Frequency(count=6),
            zero_point_byes=Frequency(count=3),
            full_point_byes=Frequency(count=0),
            forfeit_wins=Frequency(count=0),
            forfeit_losses=Frequency(count=0),
            unusual_results=Frequency(count=0),
        ),
        trf_path,
        seed=77,
    )
    codes = _result_codes(trf_path)
    assert codes['H'] == 6
    assert codes['Z'] == 3
    assert codes['F'] == 0
    # A forfeited board shows as a loss for one side and a win for the
    # other, so asking for none of either leaves both out.
    assert codes['+'] == 0
    assert codes['-'] == 0


@pytest.mark.unit
def test_a_forfeit_takes_both_sides_of_one_board(tmp_path: Path):
    trf_path = tmp_path / 'forfeits.trf'
    generate_tournament_file(
        TournamentSettings(
            players=20,
            rounds=5,
            full_point_byes=Frequency(count=0),
            half_point_byes=Frequency(count=0),
            zero_point_byes=Frequency(count=0),
            forfeit_wins=Frequency(count=0),
            forfeit_losses=Frequency(count=3),
            unusual_results=Frequency(count=0),
        ),
        trf_path,
        seed=21,
    )
    codes = _result_codes(trf_path)
    assert codes['-'] == 3
    assert codes['+'] == 3


@pytest.mark.unit
def test_the_same_seed_gives_the_same_tournament(tmp_path: Path):
    """Question 30: reproducible when a seed is given."""
    settings = TournamentSettings(players=16, rounds=5)
    first, second = tmp_path / 'a.trf', tmp_path / 'b.trf'
    generate_tournament_file(settings, first, seed=99)
    generate_tournament_file(settings, second, seed=99)
    assert first.read_bytes() == second.read_bytes()


@pytest.mark.unit
def test_without_a_seed_the_tournament_differs(tmp_path: Path):
    """Question 30: 'The generation is not random if the THP's RTG always
    produces the same TRF report when invoked with the same configurable
    parameters.'"""
    settings = TournamentSettings(players=16, rounds=5)
    first, second = tmp_path / 'c.trf', tmp_path / 'd.trf'
    generate_tournament_file(settings, first)
    generate_tournament_file(settings, second)
    assert first.read_bytes() != second.read_bytes()


@pytest.mark.unit
def test_the_file_states_the_tie_breaks_it_was_ranked_on(tmp_path: Path):
    """Question 31 asks the standings to be those of the tie-break list
    the report names, which means the report has to name one."""
    trf_path = tmp_path / 'ranked.trf'
    generate_tournament_file(
        TournamentSettings(players=18, rounds=5, tie_breaks=['PTS', 'BH/C1', 'SB']),
        trf_path,
        seed=5,
    )
    declared = [
        line
        for line in trf_path.read_text(encoding='ascii').splitlines()
        if line.startswith('212')
    ]
    assert declared == ['212 PTS,BH/C1,SB']


@pytest.mark.unit
def test_the_pairings_and_standings_are_its_own(tmp_path: Path):
    """Question 31, checked by the checker of question 21."""
    from data.input_output.trf.trf_serializer import TrfSerializer
    from data.loader import EventLoader
    from data.pairings.checkers import check_standings

    trf_path = tmp_path / 'checked.trf'
    generate_tournament_file(
        TournamentSettings(players=22, rounds=7, tie_breaks=['PTS', 'BH/C1', 'SB']),
        trf_path,
        seed=31,
    )
    from data.input_output.tournament_importer_options import FileOption
    from data.input_output.trf.trf_importer import TrfTournamentImporter
    from database.sqlite.event.event_database import EventDatabase
    from tests.test_config import TestUtils

    uniq_id = 'test-generated-check'
    TestUtils.create_event(uniq_id)
    try:
        tournament_id = TrfTournamentImporter([FileOption(trf_path)]).load_tournament(
            EventLoader().load_event(uniq_id)
        )
        EventLoader.unload_event(uniq_id)
        event = EventLoader().load_event(uniq_id)
        tournament = event.tournaments_by_id[tournament_id]
        engine = tournament.pairing_variation.engine
        for round_ in range(1, tournament.current_round + 1):
            assert not engine.pairings_diff(tournament, round_, ignore_order=True), (
                f'round {round_} is not the pairing our own engine makes'
            )
        with open(trf_path, encoding='ascii') as file:
            trf_tournament = TrfSerializer.load(file)
        diffs, unapplied, criteria, _round = check_standings(
            tournament, trf_tournament, event
        )
        assert unapplied == []
        assert criteria == ['PTS', 'BH/C1', 'SB']
        assert diffs == []
    finally:
        EventDatabase(uniq_id).delete()
