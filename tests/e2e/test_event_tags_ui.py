import pytest
from playwright.sync_api import Page, expect, APIRequestContext
from tests.test_config import TestUtils


EVENT_ID = 'test-event-tags-e2e'
OTHER_EVENT_ID = 'test-event-untagged-e2e'
TAG_NAME = 'Youth e2e'
SECOND_TAG_NAME = 'Blitz e2e'


@pytest.mark.e2e
class TestEventTags:
    def _open_event_config_modal(self, page: Page, event_uniq_id: str):
        page.goto(f'/event/{event_uniq_id}')
        page.get_by_test_id('nav-admin-event-config-tab-tab').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        return modal

    def _open_tags_modal(self, page: Page, event_uniq_id: str):
        modal = self._open_event_config_modal(page, event_uniq_id)
        modal.locator('#tags-configure-button').click()
        expect(page.locator('#event-tags-modal')).to_be_visible()

    def _create_tag(self, page: Page, name: str, color: str, add_another=False):
        page.get_by_role('button', name='Add').click()
        expect(page.get_by_test_id('tag-name')).to_be_visible()
        page.get_by_test_id('tag-name').fill(name)
        page.get_by_test_id('tag-color').fill(color)
        if add_another:
            page.locator('.dropdown-toggle-split').click()
            page.get_by_role('button', name='Create and add another').click()
            # Stays on an empty form rather than returning to the list.
            expect(page.get_by_test_id('tag-name')).to_have_value('')
        else:
            page.get_by_test_id('create-button').click()
            expect(page.locator('#event-tags-modal')).to_contain_text(name)

    def test_tag_an_event_then_filter_the_event_list(
        self, page: Page, api_request_context: APIRequestContext
    ):
        TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
        TestUtils.create_event(
            OTHER_EVENT_ID, via_api_request_context=api_request_context
        )

        # Tags are created in their own modal and land in the global registry;
        # one created from an event is selected on it.
        self._open_tags_modal(page, EVENT_ID)
        self._create_tag(page, TAG_NAME, '#123456')

        # Back restores the event modal with the tag selected.
        page.get_by_role('button', name='Back').click()
        expect(page.locator('#tags-main-container')).to_be_visible()
        expect(page.locator('#tags option[selected]')).to_have_count(1)

        page.get_by_test_id('event-form-submit-button').click()
        expect(page).to_have_url(f'/event/{EVENT_ID}/tournaments')

        # The tag survives the save and shows on the event list...
        page.goto('/current_events')
        item = page.get_by_test_id('events-item').filter(has_text=EVENT_ID)
        expect(item).to_contain_text(TAG_NAME)

        # ...and filtering on it hides the untagged event.
        page.locator('.events-tag-filter button', has_text=TAG_NAME).first.click()
        expect(
            page.get_by_test_id('events-item').filter(has_text=EVENT_ID)
        ).to_be_visible()
        expect(
            page.get_by_test_id('events-item').filter(has_text=OTHER_EVENT_ID)
        ).not_to_be_attached()

        # Clearing the filter brings the untagged event back.
        page.get_by_test_id('events-tag-filter-clear').click()
        expect(
            page.get_by_test_id('events-item').filter(has_text=OTHER_EVENT_ID)
        ).to_be_visible()

    def test_unsaved_event_edits_survive_the_tags_modal(
        self, page: Page, api_request_context: APIRequestContext
    ):
        """The tag manager is a separate modal, so the event form it was
        opened from is carried through and restored by Back."""
        modal = self._open_event_config_modal(page, EVENT_ID)
        modal.get_by_test_id('location').fill('Unsaved Location')
        modal.locator('#tags-configure-button').click()
        expect(page.locator('#event-tags-modal')).to_be_visible()
        page.get_by_role('button', name='Back').click()
        expect(page.locator('#tags-main-container')).to_be_visible()
        expect(page.get_by_test_id('location')).to_have_value('Unsaved Location')

    def test_create_and_add_another_keeps_the_form_open(
        self, page: Page, api_request_context: APIRequestContext
    ):
        self._open_tags_modal(page, EVENT_ID)
        self._create_tag(page, SECOND_TAG_NAME, '#f2c94c', add_another=True)
        # The form stays open, empty, ready for the next tag.
        expect(page.get_by_test_id('tag-name')).to_have_value('')
        # ...and the split button remembers the choice.
        expect(page.get_by_test_id('add_other-button')).to_be_visible()

    def test_tags_are_listed_alphabetically(
        self, page: Page, api_request_context: APIRequestContext
    ):
        self._open_tags_modal(page, EVENT_ID)
        names = page.locator('#event-tags-modal .badge').all_inner_texts()
        assert names == sorted(names, key=str.lower), names

    def test_deleting_a_tag_removes_it_from_the_events(
        self, page: Page, api_request_context: APIRequestContext
    ):
        self._open_tags_modal(page, EVENT_ID)
        tag_row = page.locator('#event-tags-modal .border').filter(has_text=TAG_NAME)
        tag_row.locator('button:has(.bi-trash-fill)').click()
        expect(page.locator('#event-tags-modal')).not_to_contain_text(TAG_NAME)

        # A delete carries the event form on, so Back still returns.
        page.get_by_role('button', name='Back').click()
        expect(page.locator('#tags-main-container')).to_be_visible()

        page.goto('/current_events')
        item = page.get_by_test_id('events-item').filter(has_text=EVENT_ID)
        expect(item).not_to_contain_text(TAG_NAME)
