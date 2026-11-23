"""The wizard creating a check-in screen, driven in the browser: the questions
come one after the other as the answers lead, Back returns to the previous
one, and the last one creates the screen."""

import re

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from data.loader import EventLoader
from tests.test_config import ScreenType, TestUtils

EVENT_ID = 'screen-wizard-test-event'
TOURNAMENT_NAME = 'Wizard tournament'


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
class TestScreenWizard:
    @staticmethod
    def _open_wizard(page: Page):
        page.goto(f'/event/{EVENT_ID}/screens')
        page.get_by_role('button', name='Create a screen').click()
        page.get_by_test_id(f'create-screen-type-{ScreenType.CHECK_IN.value}').click()
        page.get_by_test_id('screen-create-choice-wizard').click()
        expect(
            page.get_by_test_id('screen-wizard-question-accepts_input')
        ).to_be_visible()
        TestUtils.wait_for_htmx_idle(page)

    def test_the_wizard_creates_a_paged_check_in_screen(self, page: Page):
        self._open_wizard(page)
        back = page.get_by_test_id('screen-wizard-back')
        next_ = page.get_by_test_id('screen-wizard-next')
        create = page.get_by_test_id('screen-wizard-create')
        expect(back).to_be_hidden()
        expect(create).to_be_hidden()
        # The focus is on Next, to answer the question with Enter.
        expect(next_).to_be_focused()

        # The questions are set to their default values...
        question = page.get_by_test_id('screen-wizard-question-accepts_input')
        expect(
            question.get_by_label("Show the players' check-in status")
        ).to_be_checked()
        # ... and choosing an option answers the question.
        question.get_by_label('Let players check-in').check()
        question = page.get_by_test_id('screen-wizard-question-paged')
        expect(question).to_be_visible()
        expect(back).to_be_visible()

        # Next keeps the default option, which leads to its own next
        # question...
        expect(
            question.get_by_label('One or more tournaments, on one page')
        ).to_be_checked()
        next_.click()
        # All the tournaments are selected by default.
        tournaments = page.get_by_test_id('screen-wizard-question-switch_tournaments')
        expect(tournaments).to_be_visible()
        expect(tournaments.locator('select option:checked')).to_have_text(
            [TOURNAMENT_NAME]
        )
        # The search field of the select stays empty.
        expect(tournaments.locator('.select2-search__field')).to_have_value('')
        # ... and Back returns to the previous one to choose another.
        back.click()
        expect(question).to_be_visible()
        question.get_by_label('One tournament, over several pages').check()

        question = page.get_by_test_id('screen-wizard-question-paged_tournament')
        expect(question).to_be_visible()
        expect(next_).to_be_focused()
        # The single tournament of the event is selected by default.
        expect(question.locator('select option:checked')).to_have_text(TOURNAMENT_NAME)
        next_.click()

        question = page.get_by_test_id('screen-wizard-question-paged_method')
        question.get_by_label('A fixed number of pages').check()
        question = page.get_by_test_id('screen-wizard-question-paged_pages')
        expect(question).to_be_visible()
        question.locator('input').fill('2')

        # The questions answered are listed above, with their answers.
        answers = page.locator('.screen-wizard-answer')
        expect(answers).to_have_count(4)
        expect(
            page.get_by_test_id('screen-wizard-answer-accepts_input')
        ).to_contain_text('Let players check-in')
        expect(page.get_by_test_id('screen-wizard-answer-paged')).to_contain_text(
            'One tournament, over several pages'
        )
        expect(
            page.get_by_test_id('screen-wizard-answer-paged_tournament')
        ).to_contain_text(TOURNAMENT_NAME)
        expect(
            page.get_by_test_id('screen-wizard-answer-paged_method')
        ).to_contain_text('A fixed number of pages')

        # Back returns to the previous question, keeping the answers given.
        back.click()
        question = page.get_by_test_id('screen-wizard-question-paged_method')
        expect(question).to_be_visible()
        expect(answers).to_have_count(3)
        expect(question.get_by_label('A fixed number of pages')).to_be_checked()
        next_.click()
        question = page.get_by_test_id('screen-wizard-question-paged_pages')
        expect(question.locator('input')).to_have_value('2')
        next_.click()
        # The event has no timer: the number of columns is the last question.
        question = page.get_by_test_id('screen-wizard-question-columns')
        expect(question).to_be_visible()
        expect(create).to_be_hidden()
        question.get_by_label('2 columns').check()

        # Once the last question answered, the wizard offers to create the
        # screen (Back still returning to the last question).
        expect(page.locator('.screen-wizard-question:visible')).to_have_count(0)
        expect(answers).to_have_count(6)
        expect(next_).to_be_hidden()
        expect(create).to_be_focused()
        back.click()
        expect(question).to_be_visible()
        expect(question.get_by_label('2 columns')).to_be_checked()
        next_.click()

        # The screen is created and opened in a new tab; the page shows the
        # screens of the type.
        with page.context.expect_page() as new_tab, page.expect_navigation():
            page.get_by_test_id('screen-wizard-create-open').click()
        expect(new_tab.value).to_have_url(re.compile(f'/view/screen/{EVENT_ID}/'))
        new_tab.value.close()
        expect(page).to_have_url(
            re.compile(
                f'/event/{EVENT_ID}/screens\\?screen_type_filter='
                f'{ScreenType.CHECK_IN.value}$'
            )
        )
        expect(page.locator('.admin-screen-wizard-modal')).to_have_count(0)
        TestUtils.wait_for_htmx_idle(page)
        EventLoader.unload_event(EVENT_ID)
        event = EventLoader().load_event(EVENT_ID)
        families = event.families_by_screen_type[ScreenType.CHECK_IN.value]
        assert len(families) == 1
        assert families[0].stored_family.parts == 2
        assert families[0].stored_family.columns == 2
        assert families[0].stored_family.accepts_input
