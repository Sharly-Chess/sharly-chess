"""The live update of the layout of a screen, between its edit modal and a
device that shows it."""

import re

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from database.sqlite.event.event_database import EventDatabase
from tests.test_config import ScreenType, TestUtils

EVENT_ID = 'event-test-screen-live-update'
SCREEN_NAME = 'Live'


@pytest.fixture(autouse=True)
def screen(api_request_context: APIRequestContext):
    TestUtils.create_event(
        EVENT_ID,
        via_api_request_context=api_request_context,
        overrides={'public': True},
    )
    tournament = TestUtils.create_tournament(
        EVENT_ID,
        'Open',
        json_file='test-screens',
        via_api_request_context=api_request_context,
    )
    yield TestUtils.create_screen(
        api_request_context,
        EVENT_ID,
        SCREEN_NAME,
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id], 'public': True},
    )
    TestUtils.delete_event(EVENT_ID, via_api_request_context=api_request_context)


@pytest.mark.e2e
class TestScreenLiveUpdate:
    def test_the_modal_and_the_screen_follow_each_other(
        self, page: Page, lan_page: Page, screen
    ):
        lan_page.goto(f'/view/screen/{EVENT_ID}/{screen.uniq_id}')
        content = lan_page.locator('#user-screen-content')
        expect(content).to_be_attached()
        expect(lan_page.locator('#screen-control-panel')).to_have_count(0)

        page.goto(f'/event/{EVENT_ID}/screens?scroll_to={screen.id}&edit=true')
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        TestUtils.wait_for_htmx_idle(page)
        toggle = modal.locator('[name="live_update"]')
        notes = modal.locator('.screen-live-update-notes')
        expect(notes).to_be_hidden()

        # Turned on, the screen shows its controls.
        toggle.check()
        expect(notes).to_be_visible()
        panel = lan_page.locator('#screen-control-panel')
        expect(panel).to_be_visible()

        # The font size of the modal is shown at once by the screen.
        modal.locator('[name="font_size"]').fill('150')
        expect(content).to_have_attribute('style', re.compile('--font-size: 150;'))

        # The columns set on the screen are shown by the modal.
        columns = modal.locator('[name="columns"]')
        before = int(columns.input_value())
        lan_page.locator('#screen-controls-toggle').click()
        lan_page.locator('#screen-columns-toggle').click()
        lan_page.locator('#screen-columns-plus').click()
        expect(columns).to_have_value(str(before + 1))

        # Nothing is stored until saved, from the screen here.
        with EventDatabase(EVENT_ID) as database:
            stored = next(
                s for s in database.load_stored_screens() if s.id == screen.id
            )
        assert stored.font_size is None
        lan_page.locator('#screen-live-save').click()
        expect(toggle).not_to_be_checked()
        expect(notes).to_be_hidden()
        expect(lan_page.locator('#screen-control-panel')).to_have_count(0)
        with EventDatabase(EVENT_ID) as database:
            stored = next(
                s for s in database.load_stored_screens() if s.id == screen.id
            )
        assert (stored.font_size, stored.columns) == (150, before + 1)

    def test_closing_the_modal_brings_the_stored_layout_back(
        self, page: Page, lan_page: Page, screen
    ):
        lan_page.goto(f'/view/screen/{EVENT_ID}/{screen.uniq_id}')
        content = lan_page.locator('#user-screen-content')
        expect(content).to_be_attached()
        page.goto(f'/event/{EVENT_ID}/screens?scroll_to={screen.id}&edit=true')
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        TestUtils.wait_for_htmx_idle(page)
        modal.locator('[name="live_update"]').check()
        expect(lan_page.locator('#screen-control-panel')).to_be_visible()
        modal.locator('[name="font_size"]').fill('200')
        expect(content).to_have_attribute('style', re.compile('--font-size: 200;'))
        page.keyboard.press('Escape')
        expect(modal).to_be_hidden()
        expect(lan_page.locator('#screen-control-panel')).to_have_count(0)
        expect(content).not_to_have_attribute('style', re.compile('--font-size: 200;'))

    def test_the_alert_message_follows_the_modal(
        self, page: Page, lan_page: Page, screen
    ):
        lan_page.goto(f'/view/screen/{EVENT_ID}/{screen.uniq_id}')
        expect(lan_page.locator('#user-screen-content')).to_be_attached()
        url = f'/event/{EVENT_ID}/screens?scroll_to={screen.id}&edit=true'
        page.goto(url)
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        TestUtils.wait_for_htmx_idle(page)
        other_page = page.context.new_page()
        other_page.goto(url)
        other_modal = other_page.locator('.modal-dialog')
        expect(other_modal).to_be_visible()
        TestUtils.wait_for_htmx_idle(other_page)

        modal.locator('[name="live_update"]').check()
        expect(other_modal.locator('[name="live_update"]')).to_be_checked()
        use_default = modal.locator('[name="message_text_checkbox"]')
        if use_default.is_checked():
            use_default.uncheck()
        modal.locator('[name="message_text"]').fill('Silence please')
        expect(lan_page.locator('#alert-message-text')).to_have_text('Silence please')
        expect(other_modal.locator('[name="message_text"]')).to_have_value(
            'Silence please'
        )
        other_page.close()
