from database.sqlite.event.event_store import StoredTournament
import pytest
from playwright.sync_api import Page, expect, APIRequestContext
from tests.test_config import TestUtils
from utils.enum import Result, ScreenType


EVENT_ID = 'event-test-single-screen'
TOURNAMENT_ID = 'tournament-test-screen'


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(api_request_context, EVENT_ID)
    yield
    TestUtils.delete_event(api_request_context, EVENT_ID)


@pytest.mark.e2e
class TestSingleScreensFunctionality:
    @pytest.fixture(autouse=True)
    def tournament(self, api_request_context: APIRequestContext):
        tournament = TestUtils.create_tournament(
            api_request_context, EVENT_ID, TOURNAMENT_ID, papi_file='test-screens'
        )
        yield tournament
        TestUtils.delete_tournament(api_request_context, EVENT_ID, tournament)

    def test_create_and_delete_simple_screen(self, page: Page):
        page.goto(f'/admin/event/{EVENT_ID}/screens')
        TestUtils.button_by_text(page, 'Create a screen').click()
        TestUtils.button_by_text(page, 'Results entry').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.get_by_role('textbox', name='ID (unique):').fill('test-screen')
        modal.get_by_role('textbox', name='Name:').fill('Test Screen')
        modal.locator('button[type=submit]').click()
        card = page.locator("div.card:has-text('Test Screen')")
        expect(card).to_be_visible()

        button = card.locator('button[hx-get*="delete"]')
        button.click()
        TestUtils.button_by_text(modal, 'Delete').click()

        expect(
            page.get_by_text('Screen [test-screen] has been deleted.')
        ).to_be_visible()
        expect(page.locator("div.card:has-text('Test Screen')")).not_to_be_attached()

    def test_results_entry_screen(
        self,
        api_request_context: APIRequestContext,
        lan_page: Page,
        lan_context,
        tournament: StoredTournament,
    ):
        stored_screen = TestUtils.create_screen(
            api_request_context,
            EVENT_ID,
            'input',
            ScreenType.INPUT,
            {'init_set_tournament_id': tournament.id},
        )
        lan_page.goto(f'/user/screen/{EVENT_ID}/input')
        rows = lan_page.locator('table tbody tr')
        expect(rows).to_have_count(8)

        another_lan_page = lan_context.new_page()
        another_lan_page.goto(f'/user/screen/{EVENT_ID}/input')
        other_page_rows = another_lan_page.locator('table tbody tr')

        # Test the primary result button

        players = [
            {'name': 'ALYX', 'result': Result.GAIN, 'button_text': '1 - 0'},
            {'name': 'BRUNO', 'result': Result.DRAW, 'button_text': '½ - ½'},
            {'name': 'MARIA', 'result': Result.LOSS, 'button_text': '0 - 1'},
        ]

        for i, player in enumerate(players):
            row = rows.filter(has_text=player['name'])
            expect(row.locator('td.score')).to_contain_text(f'#{i + 1}')

            row.click()
            modal = lan_page.locator('.modal-dialog')
            expect(modal).to_be_visible()
            modal.locator(f'button:has-text("{player["button_text"]}")').click()

            # Test that the page is updated
            expect(row.locator('td.score')).to_contain_text(str(player['result']))

            # That the other page is refreshed
            other_row = other_page_rows.filter(has_text=player['name'])
            expect(other_row.locator('td.score')).to_contain_text(str(player['result']))

        TestUtils.delete_screen(api_request_context, EVENT_ID, stored_screen.id)

    def test_boards_screen(
        self,
        tournament,
        page: Page,
        lan_page: Page,
        api_request_context: APIRequestContext,
    ):
        TestUtils.create_screen(
            api_request_context,
            EVENT_ID,
            'pairings',
            ScreenType.BOARDS,
            {'init_set_tournament_id': tournament.id},
        )
        lan_page.goto(f'/user/screen/{EVENT_ID}/pairings')
        rows = lan_page.locator('table tbody tr')
        expect(rows).to_have_count(8)

        row = rows.filter(has_text='ALYX')
        expect(row.locator('td.score')).to_contain_text('#1')

        # Update the first row for some possible results, and check that the result is updated on the screen
        for r in [Result.LOSS, Result.DRAW, Result.GAIN]:
            set_result = api_request_context.put(
                f'/admin/pairing/set-result/{EVENT_ID}/{tournament.id}/1/1/{r.value}'
            )
            assert set_result.ok
            expect(row.locator('td.score')).to_contain_text(str(r))

    def test_players_screen(
        self,
        lan_page: Page,
        api_request_context: APIRequestContext,
        tournament: StoredTournament,
    ):
        TestUtils.create_screen(
            api_request_context,
            EVENT_ID,
            'players',
            ScreenType.PLAYERS,
            {'init_set_tournament_id': tournament.id},
        )
        lan_page.goto(f'/user/screen/{EVENT_ID}/players')
        rows = lan_page.locator('table tbody tr')
        expect(rows).to_have_count(16)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('ALYX')
        expect(last_row).to_contain_text('STEPHAN')
