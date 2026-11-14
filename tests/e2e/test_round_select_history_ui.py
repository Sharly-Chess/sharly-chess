"""The round and tournament selects of the pairings tab are drawn once when
the page is shown again with the browser's Back button."""

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from data.loader import EventLoader
from database.sqlite.event.event_store import StoredPlayer
from tests.test_config import TestUtils

EVENT_ID = 'round-select-history-ui'


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    for name in ('Open', 'Rapid'):
        TestUtils.create_tournament(EVENT_ID, name, overrides={'rounds': 3})
    event = EventLoader().load_event(EVENT_ID)
    for name in ('Open', 'Rapid'):
        tournament = event.tournaments_by_name[name]
        for index in range(4):
            event.add_player(
                StoredPlayer(id=None, last_name=f'{name.upper()}{index + 1}'),
                [tournament],
            )
    yield
    TestUtils.delete_event(EVENT_ID)


@pytest.mark.e2e
def test_back_to_the_pairings_draws_each_select_once(page: Page):
    tournament_id = EventLoader().load_event(EVENT_ID).tournaments_by_name['Open'].id
    page.goto(f'/event/{EVENT_ID}/pairings/{tournament_id}/1')
    groups = page.locator('#round-controls .round-controls-group')
    expect(groups.nth(0).locator('.select2-container')).to_have_count(1)
    expect(groups.nth(1).locator('.select2-container')).to_have_count(1)

    page.get_by_test_id('nav-admin-event-players-tab-tab').click()
    TestUtils.wait_for_htmx_idle(page)
    expect(page.locator('#round-controls')).to_have_count(0)

    page.go_back()
    expect(page.locator('#round-controls')).to_have_count(1)
    TestUtils.wait_for_htmx_idle(page)
    expect(groups.nth(0).locator('.select2-container')).to_have_count(1)
    expect(groups.nth(1).locator('.select2-container')).to_have_count(1)
