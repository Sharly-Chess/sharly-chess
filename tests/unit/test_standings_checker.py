"""The standings half of the pairing and tie-break checker.

FIDE C.04.A Annex 3 asks (question 21) that the checker's command line
take a TRF26 file and report "which pairings are inconsistent with the
rules for each round and which positions in the standings do not reflect
the order obtained by applying the tie-breaks". The pairings half is
checked by re-pairing each round; these tests cover the other half.

The file used is a tie-break exercise exported as TRF26, whose rank field
is then edited to state an order the criteria do not give.
"""

from pathlib import Path

import pytest

from data.input_output.tournament_exporters import Trf26TournamentExporter
from data.input_output.trf.trf_serializer import TrfSerializer
from data.loader import EventLoader
from data.pairings.checkers import check_standings
from tests.test_config import TestUtils

EVENT_ID = 'test-standings-checker'
TOURNAMENT_NAME = 'tournament'


def _restated_ranks(text: str, swap: dict[int, int]) -> str:
    """The same file with the rank of each listed position replaced."""
    lines = []
    for line in text.splitlines():
        if line.startswith('001'):
            rank = int(line[85:89])
            if rank in swap:
                line = f'{line[:85]}{swap[rank]:4d}{line[89:]}'
        lines.append(line)
    return '\n'.join(lines) + '\n'


@pytest.fixture
def exported(tmp_path: Path):
    """A ranked tournament and its TRF26 export."""
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(EVENT_ID, TOURNAMENT_NAME, json_file='tec-swiss')
    event = EventLoader().load_event(EVENT_ID)
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    exporter = Trf26TournamentExporter()
    trf_path = tmp_path / 'tournament.trf'
    with open(trf_path, 'w', encoding=exporter.file_encoding) as file:
        exporter.dump_to_file(file, tournament)
    yield event, tournament, trf_path
    TestUtils.delete_event(EVENT_ID)


def _check(event, tournament, text: str):
    trf_tournament = TrfSerializer.loads(text)
    return check_standings(tournament, trf_tournament, event)


@pytest.mark.unit
def test_the_standings_we_wrote_are_the_order_the_criteria_give(exported):
    event, tournament, trf_path = exported
    diffs, unapplied, criteria, round_ = _check(
        event, tournament, trf_path.read_text(encoding='ascii')
    )
    assert diffs == []
    assert unapplied == []
    assert criteria == ['PTS']
    assert round_ == tournament.rounds


@pytest.mark.unit
def test_a_position_the_criteria_reverse_is_reported(exported):
    """The winner and the last player are given each other's rank. Both
    positions contradict the points, and both are reported."""
    event, tournament, trf_path = exported
    text = _restated_ranks(trf_path.read_text(encoding='ascii'), {1: 16, 16: 1})
    diffs, unapplied, _criteria, _round = _check(event, tournament, text)
    assert unapplied == []
    assert len(diffs) == 2
    first = diffs[0]
    assert first.position == 1
    assert first.player.points < first.next_player.points


@pytest.mark.unit
def test_participants_the_criteria_leave_level_may_be_ordered_any_way(exported):
    """Ranked on the points alone, four players are level on 3.5 and the
    export gives them one shared rank. A file that numbers such a group
    from 2 to 5 instead, in any order, has broken the tie by lot (C.07
    Art. 4.2) and states nothing the criteria contradict."""
    event, tournament, trf_path = exported
    text = trf_path.read_text(encoding='ascii')
    tied = sorted(
        line[4:8].strip()
        for line in text.splitlines()
        if line.startswith('001') and int(line[85:89]) == 2
    )
    assert len(tied) == 4, 'the export shares one rank between the four on 3.5'
    # Number them 5, 4, 3, 2 -- an order of the tie nothing here produced.
    lines = []
    for line in text.splitlines():
        if line.startswith('001') and line[4:8].strip() in tied:
            lines.append(
                f'{line[:85]}{5 - tied.index(line[4:8].strip()):4d}{line[89:]}'
            )
        else:
            lines.append(line)
    diffs, unapplied, _criteria, _round = _check(
        event, tournament, '\n'.join(lines) + '\n'
    )
    assert unapplied == []
    assert diffs == []


@pytest.mark.unit
def test_a_criterion_we_cannot_apply_stops_the_check(exported):
    """Checking against a shorter list than the file names would pass for
    the wrong reason, so the criterion is reported instead."""
    event, tournament, trf_path = exported
    text = trf_path.read_text(encoding='ascii').replace('212 PTS', '212 PTS,NOSUCHTB')
    diffs, unapplied, _criteria, _round = _check(event, tournament, text)
    assert unapplied == ['NOSUCHTB']
    assert diffs == []


@pytest.mark.unit
def test_the_criteria_checked_against_are_the_ones_the_file_names(exported):
    event, tournament, trf_path = exported
    text = trf_path.read_text(encoding='ascii').replace('212 PTS', '212 PTS,BH/C1,SB')
    diffs, unapplied, criteria, _round = _check(event, tournament, text)
    assert unapplied == []
    assert criteria == ['PTS', 'BH/C1', 'SB']
    assert diffs == []
