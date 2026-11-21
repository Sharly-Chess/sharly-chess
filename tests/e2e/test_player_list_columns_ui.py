"""The player list and the check-in list let the arbiter choose which
optional columns to print. Each document keeps its own choice, plugin columns
join the list, and the pairing number, FIDE ID and national ID are offered but
left out unless turned on."""

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from data.loader import EventLoader
from database.sqlite.event.event_store import StoredPlayer
from tests.test_config import TestUtils

EVENT_ID = 'player-list-columns-ui'
TOURNAMENT = 'Open'


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    TestUtils.create_tournament(EVENT_ID, TOURNAMENT)
    event = EventLoader().load_event(EVENT_ID)
    tournament = event.tournaments_by_name[TOURNAMENT]
    for index in range(2):
        event.add_player(
            StoredPlayer(
                id=None,
                last_name=f'PLAYER{index + 1}',
                check_in=True,
                fide_id=10000000 + index,
                national_id=f'N{index + 1}',
            ),
            [tournament],
        )
    yield
    TestUtils.delete_event(EVENT_ID, via_api_request_context=api_request_context)


def _open_modal(page: Page) -> None:
    page.goto(f'/event/{EVENT_ID}')
    TestUtils.wait_for_htmx_bound(page, '#print-button button')
    page.locator('#print-button button').click()
    expect(page.locator('.print-modal #document')).to_be_attached()
    TestUtils.wait_for_htmx_idle(page)


@pytest.mark.e2e
class TestPlayerListColumns:
    def test_each_document_shows_its_own_column_checkboxes(self, page: Page):
        _open_modal(page)

        TestUtils.select_and_confirm(page.locator('#document'), 'player-list')
        expect(page.locator('#player-list-columns_container')).to_be_visible()
        # An on-by-default column is ticked.
        expect(page.locator('#player-list-columns-rating')).to_be_checked()
        # The new columns are offered but left out by default.
        expect(page.locator('#player-list-columns-pairing_number')).not_to_be_checked()
        expect(page.locator('#player-list-columns-fide_id')).not_to_be_checked()
        expect(page.locator('#player-list-columns-national_id')).not_to_be_checked()

        TestUtils.select_and_confirm(page.locator('#document'), 'player-checkin-list')
        expect(page.locator('#player-checkin-list-columns_container')).to_be_visible()
        expect(page.locator('#player-list-columns_container')).to_be_hidden()
        # The check-in list offers its own optional columns, such as comments.
        expect(page.locator('#player-checkin-list-columns-comments')).to_be_checked()
        expect(
            page.locator('#player-checkin-list-columns-national_id')
        ).not_to_be_checked()

    def test_the_list_prints_only_the_chosen_columns(self, page: Page):
        # The default list leaves the new columns out.
        page.goto(f'/document-view/{EVENT_ID}/player-list')
        headers = page.locator('.player-header .header')
        expect(headers.filter(has_text='FIDE')).to_have_count(0)
        expect(headers.filter(has_text='Nat. ID')).to_have_count(0)

        # Turning them on adds their columns.
        page.goto(
            f'/document-view/{EVENT_ID}/player-list'
            '?options=player-list-columns=pairing_number;fide_id;national_id'
        )
        headers = page.locator('.player-header .header')
        expect(headers.filter(has_text='FIDE')).to_have_count(1)
        expect(headers.filter(has_text='Nat. ID')).to_have_count(1)
        expect(page.locator('.player-table')).to_contain_text('10000000')
        expect(page.locator('.player-table')).to_contain_text('N1')
