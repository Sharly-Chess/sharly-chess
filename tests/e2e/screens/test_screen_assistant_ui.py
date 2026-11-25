"""The screen setup assistant, driven in the browser: the goals open the
questions, which come one after the other as the answers lead, the stage
rail gathers the answers given, Back returns to the previous question (and
to the goals from the first one), and the last question creates everything,
channel included."""

import re

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from data.loader import EventLoader
from tests.test_config import ScreenType, TestUtils

EVENT_ID = 'screen-assistant-test-event'
TOURNAMENT_NAME = 'Assistant tournament'


@pytest.fixture(autouse=True)
def tournament(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    yield TestUtils.create_tournament(
        EVENT_ID,
        TOURNAMENT_NAME,
        via_api_request_context=api_request_context,
    )
    TestUtils.delete_event(EVENT_ID, via_api_request_context=api_request_context)


@pytest.mark.e2e
class TestScreenAssistant:
    @staticmethod
    def _open_assistant(page: Page):
        page.goto(f'/event/{EVENT_ID}/screens')
        page.get_by_role('button', name='Create a screen').click()
        page.get_by_test_id('create-screen-assistant').click()
        expect(page.get_by_test_id('screen-assistant')).to_be_visible()
        TestUtils.wait_for_htmx_idle(page)

    def test_the_assistant_creates_a_paged_screen_on_a_new_channel(self, page: Page):
        self._open_assistant(page)
        # The goals are offered; the first question of the chosen goal opens.
        page.get_by_test_id('screen-assistant-goal-check-in').click()
        question = page.get_by_test_id('screen-assistant-question-paged')
        expect(question).to_be_visible()
        TestUtils.wait_for_htmx_idle(page)
        back = page.get_by_test_id('screen-assistant-back')
        next_ = page.get_by_test_id('screen-assistant-next')
        expect(next_).to_be_focused()
        # The goal is the first answer of the rail; Back returns to the
        # goals from the first question.
        answers = page.locator('.screen-assistant-answer')
        expect(answers).to_have_text(['Show the check-in status'])
        back.click()
        expect(page.get_by_test_id('screen-assistant-goal-check-in')).to_be_visible()
        TestUtils.wait_for_htmx_idle(page)
        page.get_by_test_id('screen-assistant-goal-check-in').click()
        expect(question).to_be_visible()
        TestUtils.wait_for_htmx_idle(page)

        # Choosing an option answers the question. A single tournament:
        # the tournament pick answers itself, straight to the navigation,
        # where the pages turn by themselves by default.
        question.get_by_label('Over several pages').check()
        question = page.get_by_test_id('screen-assistant-question-paged_nav')
        expect(question).to_be_visible()
        expect(question.get_by_label('The pages turn by themselves')).to_be_checked()
        next_.click()

        question = page.get_by_test_id('screen-assistant-question-paged_method')
        question.get_by_label('A fixed number of pages').check()
        question = page.get_by_test_id('screen-assistant-question-paged_pages')
        expect(question).to_be_visible()
        question.locator('input').fill('2')
        next_.click()

        # The event has no timer: the channel question follows the columns.
        question = page.get_by_test_id('screen-assistant-question-columns')
        expect(question).to_be_visible()
        question.get_by_label('2 columns').check()
        question = page.get_by_test_id('screen-assistant-question-channel')
        expect(question).to_be_visible()

        # The rail gathers the answers given, under their stages; clicking
        # one returns to its question, keeping the answers.
        expect(answers).to_have_count(6)
        expect(
            page.get_by_test_id('screen-assistant-stage-content').locator(
                '.screen-assistant-answer'
            )
        ).to_have_text(
            [
                'Show the check-in status',
                'Over several pages',
                'The pages turn by themselves',
            ]
        )
        page.locator(
            '.screen-assistant-answer', has_text='A fixed number of pages'
        ).click()
        question = page.get_by_test_id('screen-assistant-question-paged_method')
        expect(question).to_be_visible()
        expect(question.get_by_label('A fixed number of pages')).to_be_checked()
        next_.click()
        expect(
            page.get_by_test_id('screen-assistant-question-paged_pages').locator(
                'input'
            )
        ).to_have_value('2')
        next_.click()
        next_.click()

        # The event has no channel yet: the assistant offers to create one.
        question = page.get_by_test_id('screen-assistant-question-channel')
        expect(question).to_be_visible()
        question.get_by_label('Create a channel for this screen').check()
        question = page.get_by_test_id('screen-assistant-question-channel_name')
        expect(question).to_be_visible()
        question.locator('input').fill('Main hall')
        next_.click()

        # Once the last question answered, the assistant sums up what will
        # be created, Create taking the place of Next beside Back, then the
        # page moves on to the screen created.
        expect(page.get_by_test_id('screen-assistant-final')).to_be_visible()
        expect(next_).to_be_hidden()
        summary = page.get_by_test_id('screen-assistant-summary')
        expect(summary).to_contain_text(TOURNAMENT_NAME)
        expect(summary).to_contain_text('Main hall')
        create = page.get_by_test_id('screen-assistant-create')
        expect(create).to_be_visible()
        expect(create).to_be_focused()
        # Back goes to the last question, and Next takes the place again.
        back.click()
        expect(create).to_be_hidden()
        expect(next_).to_be_visible()
        next_.click()
        expect(create).to_be_visible()
        with page.expect_navigation():
            create.click()
        expect(page).to_have_url(
            re.compile(f'/event/{EVENT_ID}/screens\\?scroll_to=family-\\d+$')
        )
        TestUtils.wait_for_htmx_idle(page)
        # The paged screen created is highlighted.
        expect(page.locator('.collection-item-created')).to_have_count(1)

        EventLoader.unload_event(EVENT_ID)
        event = EventLoader().load_event(EVENT_ID)
        families = event.families_by_screen_type[ScreenType.CHECK_IN.value]
        assert len(families) == 1
        assert families[0].stored_family.parts == 2
        assert families[0].stored_family.columns == 2
        assert not families[0].stored_family.accepts_input
        channels = list(event.display_controllers_by_id.values())
        assert len(channels) == 1
        assert channels[0].name == 'Main hall'
        assert channels[0].family_id is None
        assert channels[0].stored_display_controller.item_family_ids == [families[0].id]
