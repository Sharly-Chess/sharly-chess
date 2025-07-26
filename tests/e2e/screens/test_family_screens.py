from database.sqlite.event.event_store import StoredTournament
import pytest
from playwright.sync_api import Page, expect, APIRequestContext
from tests.test_config import TestUtils
from utils.enum import Result, ScreenType


EVENT_ID = 'event-test-family-screen'
TOURNAMENT_ID = 'tournament-test-screen'
FAMILY_ID = 'test-family'


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(api_request_context, EVENT_ID)
    yield
    TestUtils.delete_event(api_request_context, EVENT_ID)


@pytest.mark.e2e
class TestFamilyScreensFunctionality:
    @pytest.fixture(autouse=True)
    def tournament(self, api_request_context: APIRequestContext):
        tournament = TestUtils.create_tournament(
            api_request_context, EVENT_ID, TOURNAMENT_ID, papi_file='test-screens'
        )
        yield tournament
        TestUtils.delete_tournament(api_request_context, EVENT_ID, tournament)

    def test_create_and_delete_family_screen(self, page: Page):
        page.goto(f'/admin/event/{EVENT_ID}/families')
        TestUtils.button_by_text(page, 'Create a screen family').click()
        TestUtils.button_by_text(page, 'Results entry').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.get_by_role('textbox', name='ID (unique):').fill(FAMILY_ID)
        modal.get_by_role('textbox', name='Name:').fill('Test Family')
        modal.locator('button[type=submit]').click()
        card = page.locator("div.card:has-text('Test Family')")
        expect(card).to_be_visible()

        button = card.locator('button[hx-get*="delete"]')
        button.click()
        TestUtils.button_by_text(modal, 'Delete').click()

        expect(page.locator("div.card:has-text('Test Family')")).not_to_be_attached()

    def test_results_entry_family_by_parts(
        self,
        tournament: StoredTournament,
        lan_page: Page,
        api_request_context: APIRequestContext,
    ):
        stored_family = TestUtils.create_family(
            api_request_context,
            EVENT_ID,
            tournament,
            FAMILY_ID,
            ScreenType.INPUT,
            {'parts': 2},
        )
        lan_page.goto(f'/user/screen/{EVENT_ID}/{FAMILY_ID}:001')
        rows = lan_page.locator('table tbody tr')
        expect(rows).to_have_count(4)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('ALYX')
        expect(last_row).to_contain_text('DAVID')

        lan_page.goto(f'/user/screen/{EVENT_ID}/{FAMILY_ID}:002')
        rows = lan_page.locator('table tbody tr')
        expect(rows).to_have_count(4)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('HELEN')
        expect(last_row).to_contain_text('IRINA')

        last_row.click()
        modal = lan_page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.locator('button:has-text("IRINA")').click()

        # Test that the page is updated
        expect(last_row.locator('td.score')).to_contain_text(str(Result.LOSS))

        TestUtils.delete_family(api_request_context, EVENT_ID, stored_family.id)

    def test_results_entry_family_by_rows(
        self,
        tournament: StoredTournament,
        lan_page: Page,
        api_request_context: APIRequestContext,
    ):
        stored_family = TestUtils.create_family(
            api_request_context,
            EVENT_ID,
            tournament,
            FAMILY_ID,
            ScreenType.INPUT,
            {'number': 2},
        )
        lan_page.goto(f'/user/screen/{EVENT_ID}/{FAMILY_ID}:001')
        rows = lan_page.locator('table tbody tr')
        expect(rows).to_have_count(2)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('ALYX')
        expect(last_row).to_contain_text('BRUNO')

        lan_page.goto(f'/user/screen/{EVENT_ID}/{FAMILY_ID}:004')
        rows = lan_page.locator('table tbody tr')
        expect(rows).to_have_count(2)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('GENEVIEVE')
        expect(last_row).to_contain_text('IRINA')

        TestUtils.delete_family(api_request_context, EVENT_ID, stored_family.id)

    def test_boards_family_by_parts(
        self,
        tournament: StoredTournament,
        lan_page: Page,
        api_request_context: APIRequestContext,
    ):
        stored_family = TestUtils.create_family(
            api_request_context,
            EVENT_ID,
            tournament,
            FAMILY_ID,
            ScreenType.BOARDS,
            {'parts': 2},
        )
        lan_page.goto(f'/user/screen/{EVENT_ID}/{FAMILY_ID}:001')
        rows = lan_page.locator('table tbody tr')
        expect(rows).to_have_count(4)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('ALYX')
        expect(last_row).to_contain_text('DAVID')

        lan_page.goto(f'/user/screen/{EVENT_ID}/{FAMILY_ID}:002')
        rows = lan_page.locator('table tbody tr')
        expect(rows).to_have_count(4)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('HELEN')
        expect(last_row).to_contain_text('IRINA')

        TestUtils.delete_family(api_request_context, EVENT_ID, stored_family.id)

    def test_boards_family_by_rows(
        self,
        tournament: StoredTournament,
        lan_page: Page,
        api_request_context: APIRequestContext,
    ):
        stored_family = TestUtils.create_family(
            api_request_context,
            EVENT_ID,
            tournament,
            FAMILY_ID,
            ScreenType.BOARDS,
            {'number': 2},
        )
        lan_page.goto(f'/user/screen/{EVENT_ID}/{FAMILY_ID}:001')
        rows = lan_page.locator('table tbody tr')
        expect(rows).to_have_count(2)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('ALYX')
        expect(last_row).to_contain_text('BRUNO')

        lan_page.goto(f'/user/screen/{EVENT_ID}/{FAMILY_ID}:004')
        rows = lan_page.locator('table tbody tr')
        expect(rows).to_have_count(2)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('GENEVIEVE')
        expect(last_row).to_contain_text('IRINA')

        TestUtils.delete_family(api_request_context, EVENT_ID, stored_family.id)

    def test_players_family_by_parts(
        self,
        tournament: StoredTournament,
        lan_page: Page,
        api_request_context: APIRequestContext,
    ):
        stored_family = TestUtils.create_family(
            api_request_context,
            EVENT_ID,
            tournament,
            FAMILY_ID,
            ScreenType.PLAYERS,
            {'parts': 2},
        )
        lan_page.goto(f'/user/screen/{EVENT_ID}/{FAMILY_ID}:001')
        rows = lan_page.locator('table tbody tr')
        expect(rows).to_have_count(8)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('ALYX')
        expect(last_row).to_contain_text('IRINA')

        lan_page.goto(f'/user/screen/{EVENT_ID}/{FAMILY_ID}:002')
        rows = lan_page.locator('table tbody tr')
        expect(rows).to_have_count(8)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('JESSICA')
        expect(last_row).to_contain_text('STEPHAN')

        TestUtils.delete_family(api_request_context, EVENT_ID, stored_family.id)

    def test_players_family_by_rows(
        self,
        tournament: StoredTournament,
        lan_page: Page,
        api_request_context: APIRequestContext,
    ):
        stored_family = TestUtils.create_family(
            api_request_context,
            EVENT_ID,
            tournament,
            FAMILY_ID,
            ScreenType.PLAYERS,
            {'number': 2},
        )
        lan_page.goto(f'/user/screen/{EVENT_ID}/{FAMILY_ID}:001')
        rows = lan_page.locator('table tbody tr')
        expect(rows).to_have_count(2)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('ALYX')
        expect(last_row).to_contain_text('BRUNO')

        lan_page.goto(f'/user/screen/{EVENT_ID}/{FAMILY_ID}:008')
        rows = lan_page.locator('table tbody tr')
        expect(rows).to_have_count(2)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('REINE')
        expect(last_row).to_contain_text('STEPHAN')

        TestUtils.delete_family(api_request_context, EVENT_ID, stored_family.id)
