"""The application, driven over HTTP in this process.

Litestar's test client calls the same handlers the server does, without
a browser or a socket, so the answers to a bad form or a missing record
can be asserted in a millisecond.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from litestar import Litestar
from litestar.testing import TestClient
from litestar.types import Receive, Scope, Send

from common.logger import set_logging_config
from common.network import LOCALHOST_IP
import contextlib

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from tests.unit.http.client import ApiClient
from utils.enum import EventType, Result
from web.server_engine import ServerEngine


class FromLocalhost:
    """The application grants the machine it runs on the administrator's
    rights, and the test client calls itself ``testclient``."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] in ('http', 'websocket'):
            scope['client'] = (LOCALHOST_IP, 0)
        await self.app(scope, receive, send)


class FromTheNetwork:
    """A visitor on the venue's network, who is granted nothing the
    application does not grant every client."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] in ('http', 'websocket'):
            scope['client'] = (LAN_IP, 0)
        await self.app(scope, receive, send)


LAN_IP = '192.168.1.25'


@pytest.fixture(scope='module')
def app() -> Litestar:
    return ServerEngine(handle_signals=False).build_app(set_logging_config())


@pytest.fixture(scope='module')
def http(app: Litestar) -> Iterator[TestClient]:
    with TestClient(FromLocalhost(app)) as client:
        yield client


@pytest.fixture
def lan(app: Litestar) -> Iterator[TestClient]:
    """A client of its own, so a session signed in by one test is not
    carried into the next."""
    with TestClient(FromTheNetwork(app)) as client:
        yield client


@pytest.fixture(scope='module')
def api(http: TestClient) -> ApiClient:
    return ApiClient(http)


TEAM_EVENT_ID = 'test-team-round-robin-http'


@pytest.fixture
def team_round_robin() -> Iterator[int]:
    """Four teams of two, rounds 1 and 2 played and published, round 3 to
    play: on the first board of each match white wins, the second is
    drawn."""
    TestUtils.create_event(TEAM_EVENT_ID, overrides={'event_type': EventType.TEAM})
    stored = TestUtils.create_tournament(
        TEAM_EVENT_ID,
        'Teams',
        overrides={
            'rounds': 3,
            'team_player_count': 2,
            'pairing': 'TEAM_ROUND_ROBIN_BERGER',
        },
    )
    with EventDatabase(TEAM_EVENT_ID, write=True) as database:
        for seed in range(1, 5):
            team_id = database.add_stored_team(
                StoredTeam(
                    id=None,
                    name=f'Team {seed}',
                    tournament_id=stored.id,
                    pairing_number=seed,
                    check_in=True,
                )
            )
            for index in range(2):
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
                        tournament_id=stored.id,
                        player_id=player_id,
                        pairing_number=index,
                    )
                )

    def load_tournament():
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(TEAM_EVENT_ID)
        event = EventLoader().load_event(TEAM_EVENT_ID)
        return event, event.tournaments_by_id[stored.id]

    for round_ in (1, 2):
        _event, tournament = load_tournament()
        tournament.pairing_variation.engine.generate_pairings(tournament, round_)
        _event, tournament = load_tournament()
        with EventDatabase(TEAM_EVENT_ID, write=True) as database:
            for team_board in tournament.get_round_team_boards(round_):
                for index, board in enumerate(team_board.boards):
                    white = board.optional_white_pairing
                    black = board.optional_black_pairing
                    if white is None or black is None:
                        continue
                    result = Result.WIN if index == 0 else Result.DRAW
                    white.update_result(database, result)
                    black.update_result(database, result.opposite_result)
        _event, tournament = load_tournament()
        tournament.set_published_round(round_)
    yield stored.id
    EventLoader.unload_event(TEAM_EVENT_ID)
    TestUtils.delete_event(TEAM_EVENT_ID)
