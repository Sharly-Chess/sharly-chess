"""The header of the point attribution of the tournament form, which is
folded by default, states the points the form holds."""

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from data.loader import EventLoader
from tests.test_config import TestUtils

EVENT_ID = 'tournament-form-points-ui'
TOURNAMENT_NAME = 'Points'


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    TestUtils.create_tournament(EVENT_ID, TOURNAMENT_NAME)
    yield
    TestUtils.delete_event(EVENT_ID)


@pytest.mark.e2e
def test_the_header_follows_the_points_typed_in(page: Page):
    tournament_id = (
        EventLoader().load_event(EVENT_ID).tournaments_by_name[TOURNAMENT_NAME].id
    )
    page.goto(f'/event/{EVENT_ID}/tournaments')
    page.locator(
        f'[hx-get="/tournament-modal/update/{EVENT_ID}/{tournament_id}"]'
    ).first.click()
    summary = page.locator('#points-attribution-section .collapse-button-summary')
    expect(summary).to_have_text('1 · 0.5 · 0')

    page.locator('#points-attribution-section .collapse-button').click()
    TestUtils.fill_and_confirm(page.locator('#gp-win'), '3')
    TestUtils.fill_and_confirm(page.locator('#gp-draw'), '1')
    expect(summary).to_have_text('3 · 1 · 0')

    TestUtils.fill_and_confirm(page.locator('#gp-win'), '')
    expect(summary).to_have_text('1 · 1 · 0')
