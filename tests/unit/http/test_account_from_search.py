"""Choosing a search result fills the account form with the person found."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_store import StoredPlayer
from tests.test_config import TestUtils
from web.controllers.admin.player_admin_controller import PlayerAdminController

EVENT_ID = 'test-account-from-search'


@pytest.fixture
def event() -> Iterator[None]:
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(EVENT_ID, 'first')
    TestUtils.create_tournament(EVENT_ID, 'second')
    EventLoader.unload_event(EVENT_ID)
    yield
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


@pytest.mark.unit
def test_the_person_found_fills_the_form_with_several_roles_chosen(
    http: TestClient, event: None
):
    found = StoredPlayer(id=None, last_name='FOUND', first_name='Person')
    with patch.object(
        PlayerAdminController,
        'get_search_stored_player',
        AsyncMock(return_value=(found, {})),
    ):
        response = http.post(
            f'/account-modal/from-search/{EVENT_ID}/fide/2',
            data={
                'last_name': '',
                'mail': 'found@example.org',
                'chief_tournament_ids': ['1', '2'],
            },
        )
    assert response.status_code == 200
    assert 'value="FOUND"' in response.text
    assert 'value="found@example.org"' in response.text
