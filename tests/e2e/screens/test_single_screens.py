import re

from data.event import Event
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTournament
import pytest
from playwright.sync_api import Page, expect, APIRequestContext
from tests.test_config import TestUtils
from utils.enum import Result, ScreenType


EVENT_ID = 'event-test-single-screen'
TOURNAMENT_ID = 'tournament-test-screen'
SCREEN_ID = 'test-screen'


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    yield
    TestUtils.delete_event(EVENT_ID, via_api_request_context=api_request_context)


@pytest.mark.e2e
class TestSingleScreensFunctionality:
    @pytest.fixture()
    def unpaired_tournament(self, api_request_context: APIRequestContext):
        tournament = TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_ID,
            json_file='test-screens-unpaired',
            via_api_request_context=api_request_context,
        )
        yield tournament
        TestUtils.delete_tournament(api_request_context, EVENT_ID, tournament)

    @pytest.fixture()
    def paired_tournament(self, api_request_context: APIRequestContext):
        tournament = TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_ID,
            json_file='test-screens',
            via_api_request_context=api_request_context,
        )
        yield tournament
        TestUtils.delete_tournament(api_request_context, EVENT_ID, tournament)

    def test_create_and_delete_simple_screen(
        self, page: Page, paired_tournament: StoredTournament
    ):
        page.goto(f'/event/{EVENT_ID}/screens')
        TestUtils.button_by_text(page, 'Create a screen').click()
        page.get_by_test_id('create-screen-type-input').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        name = 'Test Screen'
        modal.get_by_test_id('name').fill(name)
        modal.locator('button[type=submit]').click()

        page.get_by_test_id('accordion-screen-type-input').click()
        card = page.locator(f"div.card:has-text('{name}')")
        expect(card).to_be_visible()
        button = card.locator('button[hx-get*="delete"]')
        button.click()
        TestUtils.button_by_text(modal, 'Delete').click()
        expect(page.locator(f"div.card:has-text('{name}')")).not_to_be_attached()

    def test_check_in_screen(
        self,
        api_request_context: APIRequestContext,
        lan_page: Page,
        unpaired_tournament: StoredTournament,
    ):
        stored_screen = TestUtils.create_screen(
            api_request_context,
            EVENT_ID,
            SCREEN_ID,
            ScreenType.CHECK_IN,
            {'init_set_tournament_id': unpaired_tournament.id},
        )
        lan_page.goto(f'/view/screen/{EVENT_ID}/{SCREEN_ID}')
        rows = lan_page.locator('div.player-row')
        expect(rows).to_have_count(16)

        # Should not be checked in
        row = rows.filter(has_text='AMOS')
        expect(row.locator('i.bi-square')).to_be_visible()
        expect(row.locator('div:nth-child(1)')).to_have_attribute(
            'hx-get', re.compile(r'.*checkin-modal.*')
        )
        row.click()
        modal = lan_page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        button = TestUtils.button_by_text(modal, 'CHECK-IN')
        expect(button).to_contain_text('AMOS')
        button.click()

        # Test that the page is updated
        expect(row.locator('i.bi-check-square-fill')).to_be_visible()

        # Close check-in
        api_request_context.patch(
            f'/check-in/tournament-toggle-open/{EVENT_ID}/{unpaired_tournament.id}'
        )

        # Reload the page
        lan_page.goto(f'/view/screen/{EVENT_ID}/{SCREEN_ID}')

        # Clicking the row should not trigger a check-in
        rows = lan_page.locator('div.player-row')
        expect(rows).to_have_count(16)
        row = rows.filter(has_text='AMOS')
        expect(row).not_to_have_attribute('hx-get', re.compile(r'.*checkin-modal.*'))

        with EventDatabase(EVENT_ID) as database:
            event = Event(database.load_stored_event())
            barbara = next(
                p for p in event.players_by_id.values() if p.last_name == 'BARBARA'
            )
            marmite = next(
                p for p in event.players_by_id.values() if p.last_name == 'MARMITE'
            )

        # Test that the page is updated after a player checks in on another screen
        api_request_context.patch(
            f'/view/toggle-check-in/1/{EVENT_ID}/{SCREEN_ID}/{unpaired_tournament.id}/{barbara.id}'
        )

        row = rows.filter(has_text='BARBARA')
        expect(row.locator('i.bi-check-square-fill')).to_be_visible()

        # Test that the page is updated after a player is checked in on an admin screen
        api_request_context.patch(
            f'/player-table/check-in-player/{EVENT_ID}/{marmite.id}'
        )

        row = rows.filter(has_text='MARMITE')
        expect(row.locator('i.bi-check-square-fill')).to_be_visible()

        TestUtils.delete_screen(api_request_context, EVENT_ID, stored_screen.id)

    def test_results_entry_screen(
        self,
        api_request_context: APIRequestContext,
        lan_page: Page,
        lan_context,
        paired_tournament: StoredTournament,
    ):
        stored_screen = TestUtils.create_screen(
            api_request_context,
            EVENT_ID,
            SCREEN_ID,
            ScreenType.INPUT,
            {'init_set_tournament_id': paired_tournament.id},
        )
        lan_page.goto(f'/view/screen/{EVENT_ID}/{SCREEN_ID}')
        rows = lan_page.locator('div.board-row')
        expect(rows).to_have_count(8)

        another_lan_page = lan_context.new_page()
        another_lan_page.goto(f'/view/screen/{EVENT_ID}/{SCREEN_ID}')
        other_page_rows = another_lan_page.locator('div.board-row')

        # Test the primary result button

        players = [
            {'name': 'ALYX', 'result': Result.WIN, 'button_text': '1 - 0'},
            {'name': 'BRUNO', 'result': Result.DRAW, 'button_text': '½ - ½'},
            {'name': 'MARIA', 'result': Result.LOSS, 'button_text': '0 - 1'},
        ]
        for i, player in enumerate(players):
            lan_page.bring_to_front()
            row = rows.filter(has_text=player['name'])
            expect(row.locator('div.score')).to_contain_text(f'#{i + 1}')

            row.click()
            modal = lan_page.locator('.modal-dialog')
            expect(modal).to_be_visible()
            modal.locator(f'button:has-text("{player["button_text"]}")').click()
            expect(modal).not_to_be_visible()

            # Test that the page is updated
            expect(row.locator('div.score')).to_contain_text(str(player['result']))

            # That the other page is refreshed
            another_lan_page.bring_to_front()
            other_row = other_page_rows.filter(has_text=player['name'])
            expect(other_row.locator('div.score')).to_contain_text(
                str(player['result'])
            )

        TestUtils.delete_screen(api_request_context, EVENT_ID, stored_screen.id)

    def test_boards_screen(
        self,
        paired_tournament,
        lan_page: Page,
        api_request_context: APIRequestContext,
    ):
        TestUtils.create_screen(
            api_request_context,
            EVENT_ID,
            SCREEN_ID,
            ScreenType.BOARDS,
            {'init_set_tournament_id': paired_tournament.id},
        )
        lan_page.goto(f'/view/screen/{EVENT_ID}/{SCREEN_ID}')
        rows = lan_page.locator('div.board-row')
        expect(rows).to_have_count(8)

        row = rows.filter(has_text='ALYX')
        expect(row.locator('div.score')).to_contain_text('#1')

        # Update the first row for some possible results, and check that the result is updated on the screen
        for r in [Result.LOSS, Result.DRAW, Result.WIN]:
            set_result = api_request_context.put(
                f'/pairing/set-result/{EVENT_ID}/{paired_tournament.id}/1/1/{r.value}'
            )
            assert set_result.ok
            expect(row.locator('div.score')).to_contain_text(str(r))

    def test_players_screen(
        self,
        lan_page: Page,
        api_request_context: APIRequestContext,
        paired_tournament: StoredTournament,
    ):
        TestUtils.create_screen(
            api_request_context,
            EVENT_ID,
            SCREEN_ID,
            ScreenType.PLAYERS,
            {'init_set_tournament_id': paired_tournament.id},
        )
        lan_page.goto(f'/view/screen/{EVENT_ID}/{SCREEN_ID}')
        rows = lan_page.locator('div.player-row')
        expect(rows).to_have_count(16)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('ALYX')
        expect(last_row).to_contain_text('STEPHAN')
