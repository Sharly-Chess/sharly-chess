"""The journal of an event in the browser: the note added from its modal, and
the filters select2 draws. What the server answers is covered over HTTP, in
`tests/unit/http/test_journal_http.py`."""

import pytest
from playwright.sync_api import Page, expect

from data import journal
from data.journal import JournalAction
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from tests.test_config import TestUtils
from utils.enum import Result
from web.controllers.admin.journal_admin_controller import PAGE_SIZE

EVENT_ID = 'test-journal-e2e'
TOURNAMENT_NAME = 'Open'


@pytest.fixture
def event():
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(
        EVENT_ID, TOURNAMENT_NAME, json_file='tec-swiss-unpaired'
    )
    # A tournament holds its event weakly, so each loaded event is kept.
    EventLoader.unload_event(EVENT_ID)
    loaded = EventLoader().load_event(EVENT_ID)
    loaded.tournaments_by_name[TOURNAMENT_NAME].generate_round_pairings(1)
    EventLoader.unload_event(EVENT_ID)
    loaded = EventLoader().load_event(EVENT_ID)
    tournament = loaded.tournaments_by_name[TOURNAMENT_NAME]
    board = next(
        board
        for board in tournament.get_round_boards(1)
        if board.black_tournament_player is not None
    )
    tournament.add_result(board, Result.WIN)
    yield EVENT_ID
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


@pytest.mark.e2e
def test_a_note_is_added_and_the_entries_filtered(page: Page, event: str):
    page.goto(f'/event/{event}/journal')
    entries = page.get_by_test_id('journal-entry')
    expect(entries).to_have_count(2)

    page.get_by_test_id('journal-add-note').click()
    TestUtils.fill_and_confirm(
        page.locator('#modal-wrapper textarea[name="text"]'), 'Appeal on board 1'
    )
    page.get_by_test_id('journal-note-submit').click()
    expect(entries).to_have_count(3)
    TestUtils.wait_for_htmx_idle(page)
    expect(entries.first).to_contain_text('Appeal on board 1')

    TestUtils.select_and_confirm(
        page.get_by_test_id('journal-filter-category'), 'results'
    )
    expect(entries).to_have_count(1)
    expect(entries.first).to_have_attribute('data-action', 'result_entered')


@pytest.mark.e2e
def test_an_entry_written_elsewhere_appears_on_top(page: Page, event: str):
    page.goto(f'/event/{event}/journal')
    entries = page.get_by_test_id('journal-entry')
    expect(entries).to_have_count(2)
    TestUtils.wait_for_htmx_idle(page)

    page.request.post(
        f'/event/{event}/journal/note', form={'text': 'Written elsewhere'}
    )

    expect(entries).to_have_count(3)
    expect(entries.first).to_contain_text('Written elsewhere')


@pytest.mark.e2e
def test_scrolling_to_the_end_loads_the_older_entries(page: Page, event: str):
    with EventDatabase(event, write=True):
        for index in range(PAGE_SIZE):
            journal.record(event, JournalAction.NOTE, text=f'Note {index}')
    page.goto(f'/event/{event}/journal')
    entries = page.get_by_test_id('journal-entry')
    expect(entries).to_have_count(PAGE_SIZE)

    entries.last.scroll_into_view_if_needed()

    expect(entries).to_have_count(PAGE_SIZE + 2)
    expect(page.get_by_test_id('journal-more')).to_have_count(0)


@pytest.mark.e2e
def test_a_new_kind_of_entry_joins_the_filters(page: Page, event: str):
    page.goto(f'/event/{event}/journal')
    category = page.get_by_test_id('journal-filter-category')
    expect(page.get_by_text('Category:')).to_be_visible()
    expect(category.locator('option[value="notes"]')).to_have_count(0)
    TestUtils.wait_for_htmx_idle(page)

    page.request.post(f'/event/{event}/journal/note', form={'text': 'A remark'})

    expect(category.locator('option[value="notes"]')).to_have_count(1)
