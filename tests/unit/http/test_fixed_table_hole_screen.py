"""A boards screen of a fixed-table (Molter) team tournament renders every
round, including the rounds where a short-handed team leaves an empty seat on
the white side of a board.

The board is seated by the fixed table, so a team fielding fewer players than
there are boards leaves a lineup hole; the colours alternate from round to
round, so the empty seat is black in one round and white in the next.
"""

import contextlib
from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTournamentPlayer,
)
from plugins.ffe import NATIONAL_SOURCE_ID
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from utils.enum import EventType, Result, ScoreType

EVENT_ID = 'test-fixed-table-hole-screen'
TOURNAMENT_NAME = 'Molter'
SCREEN_ID = 'fixed-table-hole-screen'


def _reload(stored_id: int) -> tuple[Event, Tournament]:
    with contextlib.suppress(KeyError):
        EventLoader.unload_event(EVENT_ID)
    event = EventLoader().load_event(EVENT_ID)
    return event, event.tournaments_by_id[stored_id]


@pytest.fixture
def tournament(api: ApiClient) -> Iterator[Tournament]:
    """Three teams of four over four boards, the first team fielding only
    three players, paired on the standard Molter table; a boards screen takes
    results and records illegal moves."""
    TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
    stored = TestUtils.create_tournament(
        EVENT_ID,
        TOURNAMENT_NAME,
        overrides={
            'rounds': 3,
            'team_player_count': 4,
            'pairing': 'MOLTER_STANDARD',
            'primary_score': ScoreType.GAME_POINTS,
            'record_illegal_moves': 2,
            'rule_set': 'ffe-coupe-jean-claude-loubatiere',
        },
    )
    with EventDatabase(EVENT_ID, write=True) as database:
        for seed in range(1, 4):
            team_id = database.add_stored_team(
                StoredTeam(
                    id=None,
                    name=f'Team {seed}',
                    tournament_id=stored.id,
                    pairing_number=seed,
                    check_in=True,
                )
            )
            # The first team is one player short: a hole on its last board.
            for index in range(3 if seed == 1 else 4):
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=f'T{seed}P{index}',
                        team_id=team_id,
                        team_index=index,
                        check_in=True,
                        national_id=f'A{seed}{index:04d}',
                        national_source=NATIONAL_SOURCE_ID,
                    )
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=stored.id,
                        player_id=player_id,
                        pairing_number=index + 1,
                    )
                )
    assert stored.id is not None
    TestUtils.create_screen(
        api,
        EVENT_ID,
        SCREEN_ID,
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [stored.id], 'accepts_input': True},
    )
    _event, loaded = _reload(stored.id)
    yield loaded
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def _pair_and_publish(tournament: Tournament, round_: int) -> tuple[Event, Tournament]:
    tournament.pairing_variation.engine.generate_pairings(tournament, round_)
    _event, tournament = _reload(tournament.id)
    tournament.set_published_round(round_)
    return _reload(tournament.id)


def _win_everything(tournament: Tournament, round_: int) -> None:
    with EventDatabase(EVENT_ID, write=True) as database:
        for board in tournament.get_round_boards(round_):
            white = board.optional_white_pairing
            black = board.optional_black_pairing
            if white is None or black is None:
                continue
            white.update_result(database, Result.WIN)
            black.update_result(database, Result.LOSS)


@pytest.mark.unit
def test_the_boards_screen_renders_a_round_with_a_white_hole(
    http: TestClient, tournament: Tournament
):
    _event, tournament = _pair_and_publish(tournament, 1)
    first = http.get(f'/view/screen/{EVENT_ID}/{SCREEN_ID}', follow_redirects=False)
    assert first.status_code == 200, first.text[:2000]

    _win_everything(tournament, 1)

    _event, tournament = _reload(tournament.id)
    _event, tournament = _pair_and_publish(tournament, 2)
    second = http.get(f'/view/screen/{EVENT_ID}/{SCREEN_ID}', follow_redirects=False)
    assert second.status_code == 200, second.text[:2000]
