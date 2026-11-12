"""Replacing a player fills the form with the player found."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer, StoredTournamentPlayer
from tests.test_config import TestUtils
from utils.enum import Cadence
from web.controllers.admin.player_admin_controller import PlayerAdminController

EVENT_ID = 'test-player-replace'
TOURNAMENT_NAME = 'tournament'


@pytest.fixture
def player_id() -> Iterator[int]:
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(EVENT_ID, TOURNAMENT_NAME)
    with EventDatabase(EVENT_ID, write=True) as database:
        tournament_id = next(
            stored.id
            for stored in database.load_stored_tournaments()
            if stored.name == TOURNAMENT_NAME
        )
        assert tournament_id is not None
        replaced_id = database.add_stored_player(
            StoredPlayer(
                id=None,
                last_name='REPLACED',
                fide_id=1,
                ratings={Cadence.STANDARD.value: {'fide': 1458}},
            )
        )
        database.add_stored_tournament_player(
            StoredTournamentPlayer(tournament_id=tournament_id, player_id=replaced_id)
        )
    EventLoader.unload_event(EVENT_ID)
    yield replaced_id
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


@pytest.mark.unit
def test_the_player_found_brings_their_own_ratings(http: TestClient, player_id: int):
    found = StoredPlayer(
        id=None,
        last_name='FOUND',
        fide_id=2,
        ratings={Cadence.STANDARD.value: {'fide': 2823}},
    )
    with patch.object(
        PlayerAdminController,
        'get_search_stored_player',
        AsyncMock(return_value=(found, {})),
    ):
        response = http.post(
            f'/player-modal/from-search/{EVENT_ID}/fide/2',
            data={'player_id': str(player_id)},
        )
    assert response.status_code == 200
    assert 'value="2823"' in response.text
    assert '1458' not in response.text
