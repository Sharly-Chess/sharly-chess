import pytest
from playwright.sync_api import Page, expect, APIRequestContext

from database.sqlite.event.event_store import (
    StoredTournament,
    StoredScreen,
    StoredFamily,
)
from tests.test_config import ScreenType, TestUtils

EVENT_ID = 'rotator-test-event'
TOURNAMENT_ID = 'rotator-test-tournament'
SCREEN_ID = 'rotator-test-screen'
FAMILY_ID = 'rotator-test-family'
ROTATOR_NAME = 'rotator-test-rotator'


@pytest.fixture(autouse=True)
def setup(api_request_context: APIRequestContext):
    # Per test rather than per module: the tests create rotators through the
    # UI and delete them at the end of their body, so a test that fails early
    # would otherwise leave a name behind and fail the ones after it too.
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
        expect(page.get_by_text('The tournament has not yet started.')).to_be_visible()
