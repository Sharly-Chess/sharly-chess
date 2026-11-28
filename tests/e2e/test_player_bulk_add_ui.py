"""Picking several players in the browser. The searches and the addition are
answered by the test, so no data source is read: what the server does with
them is covered over HTTP, in `tests/unit/http/test_player_bulk_add.py`."""

import json
from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import Page, Route, expect

from tests.test_config import TestUtils

EVENT_ID = 'test-player-bulk-add-e2e'

RESULTS = {
    'alpha': [('1', 'ALPHA Ann'), ('2', 'ALPHA Bob')],
    'bravo': [('3', 'BRAVO Ben')],
}


def _results(route: Route) -> None:
    """The rows of `search_results.html` for the players of RESULTS; a club
    filter alone lists the alphas."""
    query = parse_qs(urlparse(route.request.url).query)
    search = query.get('search', [''])[0]
    if not search and 'club_filter' in query.get('filters', ['{}'])[0]:
        search = 'alpha'
    items = ''.join(
        '<li class="list-group-item d-flex list-group-item-action bulk-add-result" '
        f"data-pick='{json.dumps(['source', key, name])}' "
        'onclick="bulkAddRowClicked(event, this)">'
        f'<input type="checkbox" class="form-check-input bulk-add-check" aria-label="{name}">'
        f'<span class="bulk-add-result-content">{name}</span></li>'
        for key, name in RESULTS.get(search, [])
    )
    route.fulfill(status=200, content_type='text/html', body=items)


@pytest.fixture
def event() -> Iterator[str]:
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(EVENT_ID, 'Open')
    yield EVENT_ID
    TestUtils.delete_event(EVENT_ID)


def _open_modal(page: Page, event: str, filters: dict | None = None) -> None:
    page.route('**/search-player/**', _results)
    page.goto(f'/event/{event}/players')
    page.evaluate(
        f"localStorage.setItem('bulkAddSearchFilters', {json.dumps(json.dumps(filters or {}))})"
    )
    page.reload()
    page.locator('.sc-split-button .dropdown-toggle-split').click()
    page.get_by_test_id('bulk-add-player-button').click()
    expect(page.locator('#player-bulk-add-modal')).to_be_visible()
    TestUtils.wait_for_htmx_idle(page)


def _show(page: Page, view: str) -> None:
    page.locator(f'label[for="bulk-add-view-{view}"]').click()


@pytest.mark.e2e
def test_the_players_ticked_are_kept_across_searches_until_added(
    page: Page, event: str
):
    page.route('**/player-bulk-add/**', lambda route: route.fulfill(status=204))
    _open_modal(page, event)
    results = page.locator('#search-results .bulk-add-result')
    picks = page.get_by_test_id('bulk-add-picks').locator('li')

    search = page.locator('#search-input')
    search.press_sequentially('alpha')
    expect(results).to_have_count(2)
    TestUtils.wait_for_htmx_idle(page)
    results.nth(0).click()
    results.nth(1).locator('.bulk-add-check').check()
    expect(page.get_by_test_id('bulk-add-submit')).to_contain_text('(2)')

    search.fill('')
    search.press_sequentially('bravo')
    expect(results).to_have_count(1)
    TestUtils.wait_for_htmx_idle(page)
    results.first.click()
    expect(page.get_by_test_id('bulk-add-submit')).to_contain_text('(3)')

    # The players ticked stay ticked when they are found again
    search.fill('')
    search.press_sequentially('alpha')
    expect(results).to_have_count(2)
    TestUtils.wait_for_htmx_idle(page)
    expect(results.nth(0).locator('.bulk-add-check')).to_be_checked()
    results.nth(0).click()
    expect(results.nth(0).locator('.bulk-add-check')).not_to_be_checked()

    _show(page, 'selected')
    expect(page.locator('#search-results')).to_be_hidden()
    expect(picks).to_have_count(2)
    picks.filter(has_text='BRAVO Ben').click()
    expect(picks).to_have_count(1)
    expect(page.get_by_test_id('bulk-add-submit')).to_contain_text('(1)')

    with page.expect_request('**/player-bulk-add/**') as submitted:
        page.get_by_test_id('bulk-add-submit').click()
    players = parse_qs(submitted.value.post_data or '')['players']
    assert [json.loads(pick) for pick in players] == [['source', '2', 'ALPHA Bob']]


@pytest.mark.e2e
def test_a_club_remembered_lists_its_players_and_the_picks_are_kept(
    page: Page, event: str
):
    """The modal opens on the players of the club the filters remember, and
    once a player is ticked, only Cancel closes it."""
    _open_modal(page, event, {'club_filter': 'X'})
    modal = page.locator('#player-bulk-add-modal')
    results = page.locator('#search-results .bulk-add-result')
    expect(results).to_have_count(2)
    TestUtils.wait_for_htmx_idle(page)

    results.first.click()
    page.keyboard.press('Escape')
    page.wait_for_timeout(500)
    expect(modal).to_be_visible()

    modal.get_by_role('button', name='Cancel').click()
    expect(modal).to_be_hidden()


@pytest.mark.e2e
def test_the_list_stays_and_lists_the_players_of_the_filters_again(
    page: Page, event: str
):
    """A click elsewhere in the modal leaves the list, typing shows the
    results again from the players ticked, and emptying the box, even
    without a key, lists the players of the filters."""
    _open_modal(page, event, {'club_filter': 'X'})
    results = page.locator('#search-results .bulk-add-result')
    expect(results).to_have_count(2)
    TestUtils.wait_for_htmx_idle(page)

    page.get_by_role('heading', name='Search').click()
    expect(results.first).to_be_visible()

    _show(page, 'selected')
    search = page.locator('#search-input')
    search.press_sequentially('bravo')
    expect(results).to_have_count(1)
    expect(results.first).to_be_visible()
    TestUtils.wait_for_htmx_idle(page)
    search.evaluate(
        "input => { input.value = '';"
        " input.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    expect(results).to_have_count(2)


@pytest.mark.e2e
def test_the_bulk_filters_start_open_on_licensed_players_alone(page: Page, event: str):
    """Picking several players, the filters are open and the players no
    longer licensed left out; the search of a single player keeps its own
    filters, closed and empty."""
    page.goto(f'/event/{event}/players')
    page.evaluate('localStorage.clear()')
    page.reload()
    page.locator('.sc-split-button .dropdown-toggle-split').click()
    page.get_by_test_id('bulk-add-player-button').click()
    expect(page.locator('#player-bulk-add-modal')).to_be_visible()
    expect(page.locator('#search-criteria-collapse')).to_be_visible()
    licence = page.locator('#filter-form [name="ffe_licence_filter"]')
    expect(licence).to_have_value('B')
    page.locator('#player-bulk-add-modal').get_by_role('button', name='Cancel').click()
    expect(page.locator('#player-bulk-add-modal')).to_be_hidden()

    page.get_by_test_id('add-player-button').click()
    expect(page.locator('#modal-form')).to_be_visible()
    expect(page.locator('#search-criteria-collapse')).to_be_hidden()
    expect(page.locator('#filter-form [name="ffe_licence_filter"]')).to_have_value('')
