import pytest
from playwright.sync_api import Page, expect, APIRequestContext

from database.sqlite.event.event_store import (
    StoredTournament,
    StoredScreen,
    StoredFamily,
)
from tests.test_config import TestUtils
from utils.enum import ScreenType

EVENT_ID = 'rotator-test-event'
TOURNAMENT_ID = 'rotator-test-tournament'
SCREEN_ID = 'rotator-test-screen'
FAMILY_ID = 'rotator-test-family'
ROTATOR_NAME = 'rotator-test-rotator'


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    yield
    TestUtils.delete_event(EVENT_ID, via_api_request_context=api_request_context)


@pytest.mark.e2e
class TestRotator:
    @pytest.fixture()
    def tournament(self, api_request_context: APIRequestContext):
        tournament = TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_ID,
            via_api_request_context=api_request_context,
        )
        yield tournament
        TestUtils.delete_tournament(api_request_context, EVENT_ID, tournament)

    @pytest.fixture()
    def screen(self, api_request_context: APIRequestContext):
        screen = TestUtils.create_screen(
            api_request_context,
            EVENT_ID,
            SCREEN_ID,
            ScreenType.RESULTS,
        )
        yield screen
        TestUtils.delete_screen(api_request_context, EVENT_ID, screen.id)

    @pytest.fixture()
    def family(
        self, api_request_context: APIRequestContext, tournament: StoredTournament
    ):
        family = TestUtils.create_family(
            api_request_context,
            EVENT_ID,
            tournament,
            FAMILY_ID,
            ScreenType.BOARDS,
        )
        yield family
        TestUtils.delete_family(api_request_context, EVENT_ID, family.id)

    def test_create_and_delete_rotator(
        self,
        page: Page,
        api_request_context: APIRequestContext,
        tournament: StoredTournament,
        screen: StoredScreen,
    ):
        page.goto(f'/event/{EVENT_ID}/rotators')
        TestUtils.button_by_text(page, 'Create a rotator').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        modal.get_by_role('textbox', name='Name:').fill(ROTATOR_NAME)
        modal.locator('button[type=submit]').click()

        card = page.locator(f"div.card:has-text('{ROTATOR_NAME}')")
        expect(card).to_be_visible()

        card.locator('button[hx-get*="delete"]').click()
        TestUtils.button_by_text(modal, 'Delete').click()
        expect(
            page.get_by_text(f'Rotator [{ROTATOR_NAME}] has been deleted.')
        ).to_be_visible()
        expect(
            page.locator(f"div.card:has-text('{ROTATOR_NAME}')")
        ).not_to_be_attached()

    def test_duplicate_rotator(
        self,
        page: Page,
        api_request_context: APIRequestContext,
        tournament: StoredTournament,
        screen: StoredScreen,
        family: StoredFamily,
    ):
        rotator_id = TestUtils.create_rotator(
            api_request_context,
            EVENT_ID,
            ROTATOR_NAME,
            screen_ids=[screen.id],
            family_ids=[family.id],
        )

        page.goto(f'/event/{EVENT_ID}/rotators')
        card = page.locator(f"div.card:has-text('{ROTATOR_NAME}')")
        expect(card).to_be_visible()
        button = card.locator('button[hx-get*="clone"]')
        button.click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        name = 'Duplicated rotator'
        modal.get_by_role('textbox', name='Name:').fill(name)
        modal.locator('button[type=submit]').click()
        card = page.locator(f"div.card:has-text('{name}')")
        expect(card).to_be_visible()
        expect(card.get_by_test_id('screens-count')).to_contain_text('1')
        expect(card.get_by_test_id('families-count')).to_contain_text('1')

        card.locator('button[hx-get*="delete"]').click()
        expect(modal).to_be_visible()
        TestUtils.button_by_text(modal, 'Delete').click()
        TestUtils.delete_rotator(api_request_context, EVENT_ID, rotator_id)

    def test_create_and_delete_rotating_screen(
        self,
        page: Page,
        api_request_context: APIRequestContext,
        tournament: StoredTournament,
        screen: StoredScreen,
    ):
        rotator_id = TestUtils.create_rotator(
            api_request_context,
            EVENT_ID,
            ROTATOR_NAME,
        )

        page.goto(f'/event/{EVENT_ID}/rotators')
        card = page.locator(f"div.card:has-text('{ROTATOR_NAME}')")
        expect(card).to_be_visible()
        TestUtils.button_by_text(card, 'Screens').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()

        modal.get_by_test_id('screens-add-button').click()
        select_container = modal.get_by_test_id('screens-form-container')
        expect(select_container).to_be_visible()
        select_container.locator('.select2-selection').click()
        option = page.locator('.select2-results__option', has_text=SCREEN_ID).last
        expect(option).to_be_visible()
        option.click()
        modal.get_by_test_id('screens-submit-button').click()
        row = modal.locator(f".rotating-screen-row:has-text('{SCREEN_ID}')")
        expect(row).to_be_visible()
        row.locator('button[hx-delete*="delete"]').click()
        expect(modal.get_by_text('No screens.')).to_be_visible()

        TestUtils.delete_rotator(api_request_context, EVENT_ID, rotator_id)

    def test_rotator_screens_rotate(
        self,
        page: Page,
        api_request_context: APIRequestContext,
        tournament: StoredTournament,
        screen: StoredScreen,
        family: StoredFamily,
    ):
        rotator_id = TestUtils.create_rotator(
            api_request_context,
            EVENT_ID,
            ROTATOR_NAME,
            screen_ids=[screen.id],
            family_ids=[family.id],
            overrides={'delay': 1},
        )
        page.goto(f'/view/rotator/{EVENT_ID}/{rotator_id}')
        expect(page.get_by_text(SCREEN_ID)).to_be_visible()
        expect(page.get_by_text(f'{FAMILY_ID} (registered players)')).to_be_visible()
