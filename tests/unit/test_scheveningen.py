"""The Scheveningen pairing tables.

Every table published in Otto Milvang's "Scheveningen system" (29
September 2022) is transcribed below and compared against the generated
one, so the implementation is pinned to the paper rather than to itself.
The requirements the paper states are then checked for sizes it does not
tabulate.
"""

from unittest import TestCase

import pytest

from data.event import Event
from data.loader import EventLoader
from data.pairings.scheveningen import ScheveningenVariation, scheveningen_table
from data.print_documents.documents import (
    MolterTablePrintDocument,
    ScheveningenTablePrintDocument,
)
from data.print_documents.options import TournamentPrintOption
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTeam
from tests.test_config import TestUtils
from utils.enum import EventType

# Transcribed verbatim from the paper, "Scheveningen tables".
PUBLISHED: dict[int, str] = {
    2: """
        A1-B1 A2-B2
        B2-A1 B1-A2
    """,
    3: """
        A1-B1 A2-B2 B3-A3
        B2-A1 A2-B3 B1-A3
        A1-B3 B1-A2 A3-B2
    """,
    4: """
        A1-B1 A2-B2 B3-A3 B4-A4
        B2-A1 B1-A2 A3-B4 A4-B3
        A1-B3 A2-B4 B1-A3 B2-A4
        B4-A1 B3-A2 A3-B2 A4-B1
    """,
    # The paper prints a different 5-board table from the one its own
    # rule yields — the same schedule with the same ten colour
    # sequences, dealt to opposite sides of the match, tying on every
    # requirement it states. The rule wins, so this is Wikipedia's
    # table, which carries the same set and agrees with the rule.
    5: """
        A1-B1 A2-B2 A3-B3 B4-A4 B5-A5
        B2-A1 B3-A2 A3-B4 A4-B5 B1-A5
        A1-B3 A2-B4 B5-A3 B1-A4 A5-B2
        B4-A1 A2-B5 A3-B1 B2-A4 B3-A5
        A1-B5 B1-A2 B2-A3 A4-B3 A5-B4
    """,
    6: """
        A1-B1 B2-A2 B3-A3 A4-B4 B5-A5 A6-B6
        B2-A1 A2-B3 A3-B5 B6-A4 A5-B4 B1-A6
        A1-B3 B5-A2 B1-A3 A4-B2 A5-B6 B4-A6
        B4-A1 B6-A2 A3-B2 A4-B1 B3-A5 A6-B5
        A1-B5 A2-B4 A3-B6 B3-A4 B1-A5 B2-A6
        B6-A1 A2-B1 B4-A3 B5-A4 A5-B2 A6-B3
    """,
    7: """
        A1-B1 A2-B2 A3-B3 A4-B4 B5-A5 B6-A6 B7-A7
        B2-A1 B3-A2 B4-A3 A4-B5 A5-B6 A6-B7 B1-A7
        A1-B3 A2-B4 A3-B5 B6-A4 B7-A5 B1-A6 A7-B2
        B4-A1 B5-A2 A3-B6 A4-B7 A5-B1 B2-A6 B3-A7
        A1-B5 A2-B6 B7-A3 B1-A4 B2-A5 A6-B3 A7-B4
        B6-A1 A2-B7 A3-B1 A4-B2 B3-A5 B4-A6 B5-A7
        A1-B7 B1-A2 B2-A3 B3-A4 A5-B4 A6-B5 A7-B6
    """,
    8: """
        A1-B1 A2-B2 A3-B3 A4-B4 B5-A5 B6-A6 B7-A7 B8-A8
        B2-A1 B3-A2 B4-A3 B1-A4 A5-B6 A6-B7 A7-B8 A8-B5
        A1-B3 A2-B4 A3-B1 A4-B2 B7-A5 B8-A6 B5-A7 B6-A8
        B4-A1 B1-A2 B2-A3 B3-A4 A5-B8 A6-B5 A7-B6 A8-B7
        A1-B5 A2-B6 A3-B7 A4-B8 B1-A5 B2-A6 B3-A7 B4-A8
        B6-A1 B7-A2 B8-A3 B5-A4 A5-B2 A6-B3 A7-B4 A8-B1
        A1-B7 A2-B8 A3-B5 A4-B6 B3-A5 B4-A6 B1-A7 B2-A8
        B8-A1 B5-A2 B6-A3 B7-A4 A5-B4 A6-B1 A7-B2 A8-B3
    """,
    9: """
        A1-B1 A2-B2 A3-B3 A4-B4 A5-B5 B6-A6 B7-A7 B8-A8 B9-A9
        B2-A1 B3-A2 B4-A3 B5-A4 A5-B6 A6-B7 A7-B8 A8-B9 B1-A9
        A1-B3 A2-B4 A3-B5 A4-B6 B7-A5 B8-A6 B9-A7 B1-A8 A9-B2
        B4-A1 B5-A2 B6-A3 A4-B7 A5-B8 A6-B9 A7-B1 B2-A8 B3-A9
        A1-B5 A2-B6 A3-B7 B8-A4 B9-A5 B1-A6 B2-A7 A8-B3 A9-B4
        B6-A1 B7-A2 A3-B8 A4-B9 A5-B1 A6-B2 B3-A7 B4-A8 B5-A9
        A1-B7 A2-B8 B9-A3 B1-A4 B2-A5 B3-A6 A7-B4 A8-B5 A9-B6
        B8-A1 A2-B9 A3-B1 A4-B2 A5-B3 B4-A6 B5-A7 B6-A8 B7-A9
        A1-B9 B1-A2 B2-A3 B3-A4 B4-A5 A6-B5 A7-B6 A8-B7 A9-B8
    """,
    10: """
        A1-B1 A2-B2 A3-B3 A4-B4 B5-A5 B6-A6 B7-A7 A8-B8 B9-A9 B10-A10
        B2-A1 B1-A2 B8-A3 B3-A4 A5-B10 A6-B5 A7-B6 B4-A8 A9-B7 A10-B9
        A1-B3 A2-B8 A3-B4 A4-B10 B6-A5 B7-A6 B9-A7 A8-B1 B2-A9 B5-A10
        B4-A1 B3-A2 B10-A3 A4-B6 A5-B7 B8-A6 A7-B5 A8-B9 B1-A9 A10-B2
        A1-B5 A2-B4 B9-A3 B7-A4 B1-A5 A6-B10 B8-A7 B2-A8 A9-B3 A10-B6
        B6-A1 A2-B7 A3-B1 A4-B9 A5-B8 A6-B2 B10-A7 B5-A8 B4-A9 B3-A10
        A1-B7 B5-A2 B2-A3 B1-A4 B4-A5 B9-A6 A7-B3 A8-B10 A9-B6 A10-B8
        B8-A1 B6-A2 A3-B5 A4-B2 A5-B9 A6-B1 A7-B4 B3-A8 B10-A9 B7-A10
        A1-B9 A2-B10 A3-B7 B5-A4 B2-A5 B3-A6 B1-A7 A8-B6 A9-B8 B4-A10
        B10-A1 B9-A2 B6-A3 B8-A4 A5-B3 A6-B4 A7-B2 B7-A8 A9-B5 A10-B1
    """,
    11: """
        A1-B1 A2-B2 A3-B3 A4-B4 A5-B5 A6-B6 B7-A7 B8-A8 B9-A9 B10-A10 B11-A11
        B2-A1 B3-A2 B4-A3 B5-A4 B6-A5 A6-B7 A7-B8 A8-B9 A9-B10 A10-B11 B1-A11
        A1-B3 A2-B4 A3-B5 A4-B6 A5-B7 B8-A6 B9-A7 B10-A8 B11-A9 B1-A10 A11-B2
        B4-A1 B5-A2 B6-A3 B7-A4 A5-B8 A6-B9 A7-B10 A8-B11 A9-B1 B2-A10 B3-A11
        A1-B5 A2-B6 A3-B7 A4-B8 B9-A5 B10-A6 B11-A7 B1-A8 B2-A9 A10-B3 A11-B4
        B6-A1 B7-A2 B8-A3 A4-B9 A5-B10 A6-B11 A7-B1 A8-B2 B3-A9 B4-A10 B5-A11
        A1-B7 A2-B8 A3-B9 B10-A4 B11-A5 B1-A6 B2-A7 B3-A8 A9-B4 A10-B5 A11-B6
        B8-A1 B9-A2 A3-B10 A4-B11 A5-B1 A6-B2 A7-B3 B4-A8 B5-A9 B6-A10 B7-A11
        A1-B9 A2-B10 B11-A3 B1-A4 B2-A5 B3-A6 B4-A7 A8-B5 A9-B6 A10-B7 A11-B8
        B10-A1 A2-B11 A3-B1 A4-B2 A5-B3 A6-B4 B5-A7 B6-A8 B7-A9 B8-A10 B9-A11
        A1-B11 B1-A2 B2-A3 B3-A4 B4-A5 B5-A6 A7-B6 A8-B7 A9-B8 A10-B9 A11-B10
    """,
    12: """
        A1-B1 A2-B2 A3-B3 A4-B4 A5-B5 A6-B6 B7-A7 B8-A8 B9-A9 B10-A10 B11-A11 B12-A12
        B2-A1 B3-A2 B4-A3 B5-A4 B6-A5 B1-A6 A7-B8 A8-B9 A9-B10 A10-B11 A11-B12 A12-B7
        A1-B3 A2-B4 A3-B5 A4-B6 A5-B1 A6-B2 B9-A7 B10-A8 B11-A9 B12-A10 B7-A11 B8-A12
        B4-A1 B5-A2 B6-A3 B1-A4 B2-A5 B3-A6 A7-B10 A8-B11 A9-B12 A10-B7 A11-B8 A12-B9
        A1-B5 A2-B6 A3-B1 A4-B2 A5-B3 A6-B4 B11-A7 B12-A8 B7-A9 B8-A10 B9-A11 B10-A12
        B6-A1 B1-A2 B2-A3 B3-A4 B4-A5 B5-A6 A7-B12 A8-B7 A9-B8 A10-B9 A11-B10 A12-B11
        A1-B7 A2-B8 A3-B9 A4-B10 A5-B11 A6-B12 B1-A7 B2-A8 B3-A9 B4-A10 B5-A11 B6-A12
        B8-A1 B9-A2 B10-A3 B11-A4 B12-A5 B7-A6 A7-B2 A8-B3 A9-B4 A10-B5 A11-B6 A12-B1
        A1-B9 A2-B10 A3-B11 A4-B12 A5-B7 A6-B8 B3-A7 B4-A8 B5-A9 B6-A10 B1-A11 B2-A12
        B10-A1 B11-A2 B12-A3 B7-A4 B8-A5 B9-A6 A7-B4 A8-B5 A9-B6 A10-B1 A11-B2 A12-B3
        A1-B11 A2-B12 A3-B7 A4-B8 A5-B9 A6-B10 B5-A7 B6-A8 B1-A9 B2-A10 B3-A11 B4-A12
        B12-A1 B7-A2 B8-A3 B9-A4 B10-A5 B11-A6 A7-B6 A8-B1 A9-B2 A10-B3 A11-B4 A12-B5
    """,
    13: """
        A1-B1 A2-B2 A3-B3 A4-B4 A5-B5 A6-B6 A7-B7 B8-A8 B9-A9 B10-A10 B11-A11 B12-A12 B13-A13
        B2-A1 B3-A2 B4-A3 B5-A4 B6-A5 B7-A6 A7-B8 A8-B9 A9-B10 A10-B11 A11-B12 A12-B13 B1-A13
        A1-B3 A2-B4 A3-B5 A4-B6 A5-B7 A6-B8 B9-A7 B10-A8 B11-A9 B12-A10 B13-A11 B1-A12 A13-B2
        B4-A1 B5-A2 B6-A3 B7-A4 B8-A5 A6-B9 A7-B10 A8-B11 A9-B12 A10-B13 A11-B1 B2-A12 B3-A13
        A1-B5 A2-B6 A3-B7 A4-B8 A5-B9 B10-A6 B11-A7 B12-A8 B13-A9 B1-A10 B2-A11 A12-B3 A13-B4
        B6-A1 B7-A2 B8-A3 B9-A4 A5-B10 A6-B11 A7-B12 A8-B13 A9-B1 A10-B2 B3-A11 B4-A12 B5-A13
        A1-B7 A2-B8 A3-B9 A4-B10 B11-A5 B12-A6 B13-A7 B1-A8 B2-A9 B3-A10 A11-B4 A12-B5 A13-B6
        B8-A1 B9-A2 B10-A3 A4-B11 A5-B12 A6-B13 A7-B1 A8-B2 A9-B3 B4-A10 B5-A11 B6-A12 B7-A13
        A1-B9 A2-B10 A3-B11 B12-A4 B13-A5 B1-A6 B2-A7 B3-A8 B4-A9 A10-B5 A11-B6 A12-B7 A13-B8
        B10-A1 B11-A2 A3-B12 A4-B13 A5-B1 A6-B2 A7-B3 A8-B4 B5-A9 B6-A10 B7-A11 B8-A12 B9-A13
        A1-B11 A2-B12 B13-A3 B1-A4 B2-A5 B3-A6 B4-A7 B5-A8 A9-B6 A10-B7 A11-B8 A12-B9 A13-B10
        B12-A1 A2-B13 A3-B1 A4-B2 A5-B3 A6-B4 A7-B5 B6-A8 B7-A9 B8-A10 B9-A11 B10-A12 B11-A13
        A1-B13 B1-A2 B2-A3 B3-A4 B4-A5 B5-A6 B6-A7 A8-B7 A9-B8 A10-B9 A11-B10 A12-B11 A13-B12
    """,
}

# Double-round tables, same source. 5 is absent: the paper builds it on
# its own single-round 5 table, which is not the one generated here (see
# above); the double-round rule is pinned by 3 and 4, and the colour
# properties of a double 5 by the checks further down.
PUBLISHED_DOUBLE: dict[int, str] = {
    3: """
        A1-B1 A2-B2 B3-A3
        B2-A1 A2-B3 B1-A3
        A1-B3 B1-A2 A3-B2
        B3-A1 A2-B1 B2-A3
        A1-B2 B3-A2 A3-B1
        B1-A1 B2-A2 A3-B3
    """,
    4: """
        A1-B1 A2-B2 B3-A3 B4-A4
        B2-A1 B1-A2 A3-B4 A4-B3
        A1-B3 A2-B4 B1-A3 B2-A4
        B4-A1 B3-A2 A3-B2 A4-B1
        A1-B4 A2-B3 B2-A3 B1-A4
        B3-A1 B4-A2 A3-B1 A4-B2
        A1-B2 A2-B1 B4-A3 B3-A4
        B1-A1 B2-A2 A3-B3 A4-B4
    """,
}


def _rendered(players: int, double_round: bool) -> list[str]:
    """The generated table as one ``A1-B1 …`` string per round."""
    table = scheveningen_table(players, double_round)
    return [
        ' '.join(
            f'{p.white_team}{p.white_index}-{p.black_team}{p.black_index}'
            for p in round_
        )
        for round_ in table.rounds
    ]


def _expected(source: str, players: int) -> list[str]:
    """The transcribed table, re-joining the rounds the paper wraps over
    several lines for the wider matches."""
    words = source.split()
    return [
        ' '.join(words[start : start + players])
        for start in range(0, len(words), players)
    ]


@pytest.mark.unit
@pytest.mark.parametrize('players', sorted(PUBLISHED))
def test_the_table_matches_the_published_one(players: int):
    assert _rendered(players, False) == _expected(PUBLISHED[players], players)


@pytest.mark.unit
@pytest.mark.parametrize('players', sorted(PUBLISHED_DOUBLE))
def test_the_double_round_table_matches_the_published_one(players: int):
    assert _rendered(players, True) == _expected(PUBLISHED_DOUBLE[players], players)


@pytest.mark.unit
@pytest.mark.parametrize('players', range(2, 21))
def test_everyone_meets_everyone_exactly_once(players: int):
    """Requirement 1 and 2: every player of one team plays every player
    of the other, and no pair meets twice."""
    met: list[tuple[int, int]] = []
    for round_ in scheveningen_table(players, False).rounds:
        for pairing in round_:
            if pairing.white_team == 'A':
                met.append((pairing.white_index, pairing.black_index))
            else:
                met.append((pairing.black_index, pairing.white_index))
    assert sorted(met) == sorted(
        (a, b) for a in range(1, players + 1) for b in range(1, players + 1)
    )


@pytest.mark.unit
@pytest.mark.parametrize('players', range(2, 21))
def test_board_j_always_seats_the_same_team_a_player(players: int):
    """The board order is stable: team A sits still and team B rotates."""
    for round_ in scheveningen_table(players, False).rounds:
        for board, pairing in enumerate(round_, start=1):
            a_index = (
                pairing.white_index
                if pairing.white_team == 'A'
                else pairing.black_index
            )
            assert a_index == board


def _colours(players: int, double_round: bool) -> dict[str, list[str]]:
    """Per player, the colour held in each round, in round order."""
    colours: dict[str, list[str]] = {}
    for round_ in scheveningen_table(players, double_round).rounds:
        for pairing in round_:
            white = f'{pairing.white_team}{pairing.white_index}'
            black = f'{pairing.black_team}{pairing.black_index}'
            colours.setdefault(white, []).append('W')
            colours.setdefault(black, []).append('B')
    return colours


@pytest.mark.unit
@pytest.mark.parametrize('players', range(2, 21))
def test_each_player_is_colour_balanced(players: int):
    """Requirement 3b: the white/black difference over the whole match
    is at most one game."""
    for player, sequence in _colours(players, False).items():
        assert abs(sequence.count('W') - sequence.count('B')) <= 1, player


@pytest.mark.unit
@pytest.mark.parametrize('players', range(2, 21))
def test_a_double_round_gives_everyone_both_colours_equally(players: int):
    """Playing the return match with reversed colours evens out the
    sizes where a single round cannot."""
    for player, sequence in _colours(players, True).items():
        assert sequence.count('W') == sequence.count('B'), player


@pytest.mark.unit
@pytest.mark.parametrize('players', range(2, 21))
def test_nobody_holds_the_same_colour_three_rounds_running(players: int):
    """Requirement 3c, and the reason the return match is played back to
    front: the turn would otherwise repeat a colour three times."""
    for player, sequence in _colours(players, True).items():
        for start in range(len(sequence) - 2):
            assert len(set(sequence[start : start + 3])) > 1, (player, start)


@pytest.mark.unit
class TestScheveningenTournament(TestCase):
    """The system in a tournament, rather than the bare tables."""

    EVENT_ID = 'test-scheveningen'
    TOURNAMENT_NAME = 'match'

    def setUp(self) -> None:
        self._event: Event | None = None
        TestUtils.create_event(self.EVENT_ID, overrides={'event_type': EventType.TEAM})
        TestUtils.create_tournament(
            self.EVENT_ID,
            self.TOURNAMENT_NAME,
            overrides={
                'pairing': 'SCHEVENINGEN_STANDARD',
                'team_player_count': 4,
                'rounds': 4,
            },
        )

    def tearDown(self) -> None:
        TestUtils.delete_event(self.EVENT_ID)

    def _tournament(self):
        try:
            EventLoader.unload_event(self.EVENT_ID)
        except KeyError:
            pass
        # A Tournament holds its event weakly, so the event has to
        # outlive this call.
        event = EventLoader().load_event(self.EVENT_ID)
        self._event = event
        return event.tournaments_by_name[self.TOURNAMENT_NAME]

    def _add_teams(self, count: int) -> None:
        with EventDatabase(self.EVENT_ID, write=True) as database:
            tournament_id = next(
                stored.id
                for stored in database.load_stored_tournaments()
                if stored.name == self.TOURNAMENT_NAME
            )
            for index in range(count):
                database.add_stored_team(
                    StoredTeam(
                        id=None,
                        name=f'Team {index + 1}',
                        tournament_id=tournament_id,
                        pairing_number=index + 1,
                    )
                )

    def test_the_system_is_offered_for_team_events(self):
        tournament = self._tournament()
        assert tournament.pairing_system.id == 'SCHEVENINGEN'
        assert isinstance(tournament.pairing_variation, ScheveningenVariation)
        assert not tournament.pairing_variation.double_round

    def test_a_third_team_is_reported_rather_than_raised(self):
        """The tab reads the table on every render, so a system picked
        for a shape it cannot pair has to leave the page standing."""
        self._add_teams(3)
        tournament = self._tournament()
        engine = tournament.pairing_variation.engine
        message = engine.invalid_player_count_message(tournament)
        assert message is not None and '2' in message
        # The read-only accessors the pairings tab calls stay quiet.
        assert engine.board_references(tournament, 1) == []
        assert engine.round_seats(tournament, 1) == {}
        assert tournament.unboarded_holes(1) == []

    def test_two_teams_produce_the_table(self):
        self._add_teams(2)
        tournament = self._tournament()
        engine = tournament.pairing_variation.engine
        assert engine.invalid_player_count_message(tournament) is None
        assert engine.board_references(tournament, 1) == [
            ('A1', 'B1'),
            ('A2', 'B2'),
            ('B3', 'A3'),
            ('B4', 'A4'),
        ]

    def test_the_pairing_table_document_lists_every_round(self):
        """The whole schedule is known up front, so the document prints
        before a move is played."""
        self._add_teams(2)
        tournament = self._tournament()
        document = ScheveningenTablePrintDocument(
            options=[TournamentPrintOption(self._event, tournament.id)]
        )
        document.event = self._event
        assert document.is_available([tournament])
        document.validate_options()
        context = document.template_context
        assert context['round_names'] == ['R1', 'R2', 'R3', 'R4']
        # One row per board, one column per round.
        assert len(context['board_rows']) == 4
        assert context['board_rows'][0] == ['A1 – B1', 'B2 – A1', 'A1 – B3', 'B4 – A1']
        assert [entry['letter'] for entry in context['legend']] == ['A', 'B']

    def test_the_molter_document_is_not_offered_here(self):
        """The two share a base class; each stays with its own system."""
        self._add_teams(2)
        assert not MolterTablePrintDocument.is_available([self._tournament()])
