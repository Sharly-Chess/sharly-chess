"""A team Swiss has no FIDE mode, but logs the pairing integrity breaching
events all the same: a change to a round the next ones were paired from
asks for a confirmation and is logged, and changing the number of rounds
once started is logged without a warning. Its games are not corrected for
the rating report only."""

import contextlib
from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.event import Event
from data.loader import EventLoader
from data.pairings.systems import TeamSwissPairingSystem
from data.pibes import PibeType
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import EventType, Result
from web.controllers.admin.tournament_admin_controller import (
    TournamentAdminController,
)

EVENT_ID = 'test-team-swiss-log'
TOURNAMENT_NAME = 'tournament'
BOARDS = 2
TEAMS = 4


_loaded: list[Event] = []


def load() -> Tournament:
    """The tournament read back from its database; a tournament holds its
    event weakly, so the event is kept here."""
    with contextlib.suppress(KeyError):
        EventLoader.unload_event(EVENT_ID)
    event = EventLoader().load_event(EVENT_ID)
    _loaded[:] = [event]
    return event.tournaments_by_name[TOURNAMENT_NAME]


def play(round_: int) -> None:
    tournament = load()
    with EventDatabase(EVENT_ID, write=True) as database:
        for board in tournament.get_round_boards(round_):
            white = board.optional_white_pairing
            black = board.optional_black_pairing
            if white is None or black is None:
                if (present := white or black) is not None:
                    present.update_result(database, Result.FORFEIT_WIN)
                continue
            white.update_result(database, Result.WIN)
            black.update_result(database, Result.LOSS)


@pytest.fixture
def tournament() -> Iterator[Tournament]:
    TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
    stored_tournament = TestUtils.create_tournament(
        EVENT_ID,
        TOURNAMENT_NAME,
        overrides={
            'rounds': 3,
            'team_player_count': BOARDS,
            'pairing': 'TEAM_SWISS_STANDARD',
        },
    )
    tournament_id = stored_tournament.id
    assert tournament_id is not None
    with EventDatabase(EVENT_ID, write=True) as database:
        for seed in range(1, TEAMS + 1):
            team_id = database.add_stored_team(
                StoredTeam(
                    id=None,
                    name=f'Team{seed}',
                    tournament_id=tournament_id,
                    pairing_number=seed,
                    check_in=True,
                )
            )
            for index in range(BOARDS):
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=f'T{seed}P{index}',
                        team_id=team_id,
                        team_index=index,
                        check_in=True,
                    )
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id,
                        player_id=player_id,
                        pairing_number=index + 1,
                    )
                )
    for round_ in (1, 2, 3):
        assert load().generate_round_pairings(round_) == ''
        play(round_)
    yield load()
    _loaded.clear()
    with contextlib.suppress(KeyError):
        EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def first_game(tournament: Tournament, round_: int):
    return next(
        board
        for board in sorted(tournament.get_round_boards(round_), key=lambda b: b.index)
        if board.white_player_id is not None and board.black_player_id is not None
    )


@pytest.mark.unit
def test_a_team_swiss_logs_without_fide_mode(tournament: Tournament):
    assert not TeamSwissPairingSystem().supports_fide_mode
    assert TeamSwissPairingSystem().logs_pairing_breaches
    assert not tournament.fide_mode
    assert tournament.logs_pairing_breaches
    assert tournament.fide_mode_exit_round is None


@pytest.mark.unit
@pytest.mark.parametrize('round_', [2, 1])
def test_a_change_to_a_round_paired_from_is_logged(
    http: TestClient, tournament: Tournament, round_: int
):
    board = first_game(tournament, round_)

    http.put(
        f'/pairing/set-result/{EVENT_ID}/{tournament.id}/{round_}'
        f'/{board.identifier}/{Result.DRAW.value}'
    )

    tournament = load()
    assert tournament.boards_by_id[board.identifier].result == Result.DRAW
    assert [(pibe.type, pibe.round_) for pibe in tournament.pibes] == [
        (PibeType.CORRECTION, round_)
    ]


@pytest.mark.unit
def test_a_rounds_change_is_logged_without_a_warning(tournament: Tournament):
    stored = tournament.stored_tournament
    changed = type(stored)(**{**stored.__dict__, 'rounds': 2})

    logs, warning = TournamentAdminController._rounds_change(tournament, changed)

    assert [pibe.type for pibe in logs][:1] == [PibeType.ROUNDS]
    assert warning == {}


@pytest.mark.unit
def test_a_team_swiss_has_no_rating_report_correction(
    http: TestClient, tournament: Tournament
):
    board = first_game(tournament, 1)

    http.put(
        f'/pairing/rating-correction/{EVENT_ID}/{tournament.id}/1'
        f'/{board.identifier}/{board.white_player_id}/{Result.DRAW.value}'
    )

    assert load().rating_corrections == []
