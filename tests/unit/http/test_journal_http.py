"""The journal of the event, written by the actions done over HTTP and read
from its page."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
from litestar.testing import TestClient

from data import journal
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredAccount
from web.controllers.admin.journal_admin_controller import PAGE_SIZE
from data.journal import (
    Actor,
    Author,
    AuthorKind,
    JournalAction,
    Source,
    SourceKind,
    acting_as,
    load_journal,
)
from data.player import Player
from data.tournament import Tournament
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from tests.unit.http.conftest import LAN_IP
from tests.unit.http.events import EventUnderTest
from utils.enum import Result

EVENT_ID = 'test-journal-http'
TOURNAMENT_NAME = 'test-journal-http-tournament'
SCREEN_ID = 'test-journal-http-screen'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


@pytest.fixture
def tournament(http: TestClient) -> Iterator[Tournament]:
    EVENT.create(json_file='tec-swiss-unpaired')
    tournament = EVENT.tournament()
    http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/1')
    http.put(f'/pairings/publish/{EVENT_ID}/{tournament.id}/1')
    yield EVENT.tournament()
    EVENT.delete()


def _set_result(http: TestClient, tournament: Tournament, result: Result) -> None:
    board = tournament.get_round_boards(1)[0]
    response = http.put(
        f'/pairing/set-result/{EVENT_ID}/{tournament.id}/1/{board.id}/{result.value}'
    )
    assert response.status_code == 200


def _results(entries):
    return [entry for entry in entries if entry.category == 'results']


@pytest.mark.unit
def test_a_result_entered_by_the_administrator_is_journaled(
    http: TestClient, tournament: Tournament
):
    _set_result(http, tournament, Result.WIN)

    [entry] = _results(load_journal(EVENT_ID))
    assert entry.action == JournalAction.RESULT_ENTERED
    assert entry.author is not None
    assert entry.author.kind == AuthorKind.ADMINISTRATOR
    assert entry.source.kind == SourceKind.COMPUTER
    assert entry.tournament_id == tournament.id

    page = http.get(f'/event/{EVENT_ID}/journal')
    assert page.status_code == 200
    assert entry.sentence in page.text


@pytest.mark.unit
def test_a_result_entered_on_a_screen_names_the_screen(
    api: ApiClient, http: TestClient, lan: TestClient, tournament: Tournament
):
    TestUtils.create_screen(
        api,
        EVENT_ID,
        SCREEN_ID,
        ScreenType.BOARDS,
        {
            'init_set_tournament_ids': [tournament.id],
            'accepts_input': True,
            'public': True,
        },
    )
    board = tournament.get_round_boards(1)[0]
    response = lan.put(
        f'/view/update-result/1/{EVENT_ID}/{SCREEN_ID}/{tournament.id}/1'
        f'/{board.id}/{Result.DRAW.value}?shown={Result.NO_RESULT.value}'
    )
    assert response.status_code == 200

    [entry] = _results(load_journal(EVENT_ID))
    assert entry.author is None
    assert entry.source.kind == SourceKind.SCREEN
    assert entry.host == LAN_IP
    assert SCREEN_ID in (entry.source.name or '')


@pytest.mark.unit
def test_the_journal_is_not_shown_to_a_visitor(lan: TestClient, tournament: Tournament):
    response = lan.get(f'/event/{EVENT_ID}/journal', follow_redirects=False)
    assert response.headers['location'].endswith('/error/403')


@pytest.mark.unit
def test_a_note_is_added_then_deleted(http: TestClient, tournament: Tournament):
    response = http.post(
        f'/event/{EVENT_ID}/journal/note',
        data={'text': 'Appeal on board 1', 'tournament_id': str(tournament.id)},
    )
    assert response.status_code in (200, 201)
    [note] = [entry for entry in load_journal(EVENT_ID) if entry.is_note]
    assert note.text == 'Appeal on board 1'
    assert note.tournament_id == tournament.id
    assert 'Appeal on board 1' in http.get(f'/event/{EVENT_ID}/journal').text

    response = http.delete(f'/event/{EVENT_ID}/journal/note/{note.id}')
    assert response.status_code == 200
    assert not [entry for entry in load_journal(EVENT_ID) if entry.is_note]


@pytest.mark.unit
def test_an_empty_note_is_refused(http: TestClient, tournament: Tournament):
    http.post(f'/event/{EVENT_ID}/journal/note', data={'text': '  '})

    assert not [entry for entry in load_journal(EVENT_ID) if entry.is_note]


@pytest.mark.unit
def test_an_action_cannot_be_deleted(http: TestClient, tournament: Tournament):
    _set_result(http, tournament, Result.WIN)
    [entry] = _results(load_journal(EVENT_ID))

    response = http.delete(
        f'/event/{EVENT_ID}/journal/note/{entry.id}', follow_redirects=False
    )

    assert response.headers['location'].endswith('/error/404')
    assert _results(load_journal(EVENT_ID))


@pytest.mark.unit
def test_the_journal_downloads_as_csv(http: TestClient, tournament: Tournament):
    _set_result(http, tournament, Result.WIN)

    response = http.get(f'/event/{EVENT_ID}/journal.csv')

    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/csv')
    [entry] = _results(load_journal(EVENT_ID))
    assert entry.sentence in response.text


@pytest.mark.unit
def test_the_filters_narrow_the_entries(http: TestClient, tournament: Tournament):
    _set_result(http, tournament, Result.WIN)
    http.post(f'/event/{EVENT_ID}/journal/note', data={'text': 'A remark'})

    notes = http.get(f'/event/{EVENT_ID}/journal/entries?category=notes')
    results = http.get(f'/event/{EVENT_ID}/journal/entries?category=results')

    assert 'A remark' in notes.text
    assert 'A remark' not in results.text
    assert 'data-action="result_entered"' in results.text


@pytest.mark.unit
def test_only_the_entries_written_since_are_sent_to_add_on_top(
    http: TestClient, tournament: Tournament
):
    http.post(f'/event/{EVENT_ID}/journal/note', data={'text': 'First'})
    [first] = [entry for entry in load_journal(EVENT_ID) if entry.is_note]
    http.post(f'/event/{EVENT_ID}/journal/note', data={'text': 'Second'})

    response = http.get(f'/event/{EVENT_ID}/journal/entries?after_id={first.id}')

    assert response.headers['hx-retarget'] == '#journal-rows'
    assert response.headers['hx-reswap'] == 'afterbegin'
    assert 'Second' in response.text
    assert 'First' not in response.text


@pytest.mark.unit
def test_scrolling_to_the_end_brings_the_older_entries_a_page_at_a_time(
    http: TestClient, tournament: Tournament
):
    with EventDatabase(EVENT_ID, write=True):
        for index in range(PAGE_SIZE + 5):
            journal.record(EVENT_ID, JournalAction.NOTE, text=f'Note {index}')

    page = http.get(f'/event/{EVENT_ID}/journal')
    assert page.text.count('data-testid="journal-entry"') == PAGE_SIZE
    assert 'data-testid="journal-more"' in page.text
    oldest_shown = min(entry.id for entry in load_journal(EVENT_ID, limit=PAGE_SIZE))

    older = http.get(f'/event/{EVENT_ID}/journal/entries?before_id={oldest_shown}')

    total = len(load_journal(EVENT_ID))
    assert older.text.count('data-testid="journal-entry"') == total - PAGE_SIZE
    assert 'Note 0<' in older.text
    assert 'data-testid="journal-more"' not in older.text


@pytest.mark.unit
def test_the_older_entries_keep_to_the_filters(
    http: TestClient, tournament: Tournament
):
    _set_result(http, tournament, Result.WIN)
    http.post(f'/event/{EVENT_ID}/journal/note', data={'text': 'A remark'})
    [note] = [entry for entry in load_journal(EVENT_ID) if entry.is_note]

    older = http.get(
        f'/event/{EVENT_ID}/journal/entries?before_id={note.id + 1}&category=results'
    )

    assert 'data-action="result_entered"' in older.text
    assert 'A remark' not in older.text


def _options_key(page: str) -> str:
    return page.split('data-options-key="', 1)[1].split('"', 1)[0]


@pytest.mark.unit
def test_the_filters_are_drawn_again_when_the_journal_holds_new_options(
    http: TestClient, tournament: Tournament
):
    page = http.get(f'/event/{EVENT_ID}/journal')
    key = _options_key(page.text)
    [newest] = load_journal(EVENT_ID, limit=1)
    url = f'/event/{EVENT_ID}/journal/entries?after_id={newest.id}&options_key={key}'

    unchanged = http.get(url)
    assert 'hx-trigger-after-settle' not in unchanged.headers

    http.post(f'/event/{EVENT_ID}/journal/note', data={'text': 'A remark'})
    changed = http.get(url)
    assert 'journal-filters-stale' in changed.headers['hx-trigger-after-settle']

    filters = http.get(f'/event/{EVENT_ID}/journal/filters?category=pairings')
    assert 'value="notes"' in filters.text
    assert 'value="pairings" selected' in filters.text
    assert _options_key(filters.text) != key


@pytest.mark.unit
def test_a_staff_account_is_named_as_it_is_called_now_then_once_deleted(
    http: TestClient, tournament: Tournament
):
    event = EVENT.load()
    account = event.create_account(
        StoredAccount(id=None, active=True, first_name='Jane', last_name='ARBITER')
    )
    author = Author(AuthorKind.ACCOUNT, account.id)
    with acting_as(Actor(author, Source(SourceKind.NETWORK, host=LAN_IP))):
        journal.record(EVENT_ID, JournalAction.NOTE, text='A decision')

    event = EVENT.load()
    renamed = replace(
        event.accounts_by_id[account.id].stored_account, last_name='SMITH'
    )
    event.update_account(renamed)
    page = http.get(f'/event/{EVENT_ID}/journal')
    assert 'SMITH' in page.text
    assert 'Another device' in page.text
    assert f'Another device ({LAN_IP})' in page.text

    event = EVENT.load()
    event.delete_account(event.accounts_by_id[account.id])
    page = http.get(f'/event/{EVENT_ID}/journal')
    name = Player.player_full_name('Jane', 'SMITH')
    assert f'{name} (deleted account)' in page.text
