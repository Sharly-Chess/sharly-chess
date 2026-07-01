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
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    yield
    TestUtils.delete_event(EVENT_ID, via_api_request_context=api_request_context)


@pytest.mark.e2e
class TestFamilyScreensFunctionality:
    @pytest.fixture(autouse=True)
    def tournament(self, api_request_context: APIRequestContext):
        tournament = TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_ID,
            json_file='test-screens',
            via_api_request_context=api_request_context,
        )
        yield tournament
        TestUtils.delete_tournament(api_request_context, EVENT_ID, tournament)

    def test_create_and_delete_family_screen(self, page: Page):
        page.goto(f'/event/{EVENT_ID}/families')
        TestUtils.button_by_text(page, 'Create a multi-screen').click()
        TestUtils.button_by_text(page, 'Results entry').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()

        name = 'Test family'
        modal.get_by_test_id('name').fill(name)
        modal.locator('button[type=submit]').click()
        card = page.locator(f"div.card:has-text('{name}')")
        expect(card).to_be_visible()

        button = card.locator('button[hx-get*="delete"]')
        button.click()
        TestUtils.button_by_text(modal, 'Delete').click()
        expect(page.locator(f"div.card:has-text('{name}')")).not_to_be_attached()

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
        lan_page.goto(f'/view/screen/{EVENT_ID}/{FAMILY_ID}:001')
        rows = lan_page.locator('div.board-row')
        expect(rows).to_have_count(4)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('ALYX')
        expect(last_row).to_contain_text('DAVID')

        lan_page.goto(f'/view/screen/{EVENT_ID}/{FAMILY_ID}:002')
        rows = lan_page.locator('div.board-row')
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
        expect(last_row.locator('div.score')).to_contain_text(str(Result.LOSS))

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
        lan_page.goto(f'/view/screen/{EVENT_ID}/{FAMILY_ID}:001')
        rows = lan_page.locator('div.board-row')
        expect(rows).to_have_count(2)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('ALYX')
        expect(last_row).to_contain_text('BRUNO')

        lan_page.goto(f'/view/screen/{EVENT_ID}/{FAMILY_ID}:004')
        rows = lan_page.locator('div.board-row')
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
        lan_page.goto(f'/view/screen/{EVENT_ID}/{FAMILY_ID}:001')
        rows = lan_page.locator('div.board-row')
        expect(rows).to_have_count(4)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('ALYX')
        expect(last_row).to_contain_text('DAVID')

        lan_page.goto(f'/view/screen/{EVENT_ID}/{FAMILY_ID}:002')
        rows = lan_page.locator('div.board-row')
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
        lan_page.goto(f'/view/screen/{EVENT_ID}/{FAMILY_ID}:001')
        rows = lan_page.locator('div.board-row')
        expect(rows).to_have_count(2)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('ALYX')
        expect(last_row).to_contain_text('BRUNO')

        lan_page.goto(f'/view/screen/{EVENT_ID}/{FAMILY_ID}:004')
        rows = lan_page.locator('div.board-row')
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
        lan_page.goto(f'/view/screen/{EVENT_ID}/{FAMILY_ID}:001')
        rows = lan_page.locator('div.player-row')
        expect(rows).to_have_count(8)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('ALYX')
        expect(last_row).to_contain_text('IRINA')

        lan_page.goto(f'/view/screen/{EVENT_ID}/{FAMILY_ID}:002')
        rows = lan_page.locator('div.player-row')
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
        lan_page.goto(f'/view/screen/{EVENT_ID}/{FAMILY_ID}:001')
        rows = lan_page.locator('div.player-row')
        expect(rows).to_have_count(2)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('ALYX')
        expect(last_row).to_contain_text('BRUNO')

        lan_page.goto(f'/view/screen/{EVENT_ID}/{FAMILY_ID}:008')
        rows = lan_page.locator('div.player-row')
        expect(rows).to_have_count(2)

        first_row = rows.first
        last_row = rows.nth(-1)
        expect(first_row).to_contain_text('REINE')
        expect(last_row).to_contain_text('STEPHAN')

        TestUtils.delete_family(api_request_context, EVENT_ID, stored_family.id)
