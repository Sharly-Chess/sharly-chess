"""The Pair button of a Swiss tournament is a split button offering to pair
alone or to pair and publish at once; the browser keeps the last choice."""

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from data.loader import EventLoader
from database.sqlite.event.event_store import StoredPlayer
from tests.test_config import TestUtils

EVENT_ID = 'pair-and-publish-ui'
TOURNAMENT_NAME = 'Swiss'


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    TestUtils.create_tournament(EVENT_ID, TOURNAMENT_NAME, overrides={'rounds': 3})
    event = EventLoader().load_event(EVENT_ID)
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    for index in range(4):
        event.add_player(
            StoredPlayer(id=None, last_name=f'PLAYER{index + 1}'), [tournament]
        )
    yield
    TestUtils.delete_event(EVENT_ID)


def _published_round() -> int:
    event = EventLoader().load_event(EVENT_ID)
    return event.tournaments_by_name[TOURNAMENT_NAME].published_round


def _pair_from_menu(page: Page, item: str) -> None:
    tournament_id = (
        EventLoader().load_event(EVENT_ID).tournaments_by_name[TOURNAMENT_NAME].id
    )
    page.goto(f'/event/{EVENT_ID}/pairings/{tournament_id}/1')
    mark_present = page.get_by_role('button', name='Mark all players as "Present"')
    if mark_present.count():
        mark_present.click()
    split = page.locator('#pairing-buttons .sc-split-button')
    split.locator('.dropdown-toggle-split').click()
    split.locator('.dropdown-menu').get_by_role('button', name=item, exact=True).click()
    # The modals shown before pairing (ratings reminder, settings) are
    # confirmed until the round is paired.
    unpair = page.get_by_role('button', name='Unpair')
    modal = page.locator('#modal-wrapper .modal-footer')
    for _ in range(5):
        if unpair.is_visible():
            break
        confirm = modal.locator('button:not([data-bs-dismiss])').last
        if confirm.is_visible():
            confirm.click()
        page.wait_for_timeout(500)
    expect(unpair).to_be_visible()
    expect(page.locator('#pairings-table')).to_be_visible()


@pytest.mark.e2e
def test_pair_and_publish_is_remembered(page: Page):
    _pair_from_menu(page, 'Pair and publish')
    assert _published_round() == 1
    expect(page.get_by_role('button', name='Unpublish')).to_be_visible()

    page.get_by_role('button', name='Unpublish').click()
    expect(page.get_by_role('button', name='Publish', exact=True)).to_be_visible()
    page.get_by_role('button', name='Unpair').click()
    page.locator('#modal-wrapper').get_by_role('button', name='Proceed').click()
    expect(
        page.locator('#pairing-buttons .sc-split-button').get_by_role(
            'button', name='Pair and publish', exact=True
        )
    ).to_be_visible()

    _pair_from_menu(page, 'Pair')
    assert _published_round() == 0
    expect(page.get_by_role('button', name='Publish', exact=True)).to_be_visible()
