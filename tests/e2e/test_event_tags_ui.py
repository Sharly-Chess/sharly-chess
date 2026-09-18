import pytest
from playwright.sync_api import Page, expect, APIRequestContext
from database.sqlite.config.config_database import ConfigDatabase
from tests.test_config import TestUtils


EVENT_ID = 'test-event-tags-e2e'
OTHER_EVENT_ID = 'test-event-untagged-e2e'
TAG_NAME = 'Youth e2e'
SECOND_TAG_NAME = 'Blitz e2e'


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    TestUtils.create_event(OTHER_EVENT_ID, via_api_request_context=api_request_context)

    yield

    TestUtils.delete_event(EVENT_ID, via_api_request_context=api_request_context)
    TestUtils.delete_event(OTHER_EVENT_ID, via_api_request_context=api_request_context)


@pytest.mark.e2e
class TestEventTags:
    def _open_event_config_modal(self, page: Page, event_uniq_id: str):
        page.goto(f'/event/{event_uniq_id}')
        page.get_by_test_id('nav-admin-event-config-tab-tab').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        # .modal-dialog is a Bootstrap placeholder until htmx swaps the real
        # form in; wait for the stored location so a fill can't be overwritten.
        expect(modal.get_by_test_id('location')).to_have_value('Paris')
        return modal

    def _open_tags_modal(self, page: Page, event_uniq_id: str):
        modal = self._open_event_config_modal(page, event_uniq_id)
        # The event form is still being swapped in behind the field the opener
        # waits on, and a click landing mid-swap is lost.
        TestUtils.wait_for_htmx_idle(page)
        modal.locator('#tags-configure-button').click()
        expect(page.locator('#event-tags-modal')).to_be_visible()
        # The registry rows arrive with the swap the click started, and a
        # click on one of them before it lands is lost.
        TestUtils.wait_for_htmx_idle(page)

    @staticmethod
    def _back_to_the_event_form(page: Page):
        """Leave the tags modal for the event form it was opened from.

        Back is an htmx button, so clicking it before htmx has taken it over
        does nothing at all.
        """
        selector = '#event-tags-modal button[hx-post*="event-modal-restore"]'
        TestUtils.wait_for_htmx_bound(page, selector)
        page.locator(selector).click()
        expect(page.locator('#tags-main-container')).to_be_visible()

    @staticmethod
    def _goto_event_list(page: Page):
        """Leave for the event list.

        The actions this module drives target the body, so a navigation
        started while one of them is still in flight is aborted.
        """
        TestUtils.wait_for_htmx_idle(page)
        page.goto('/current_events')

    @staticmethod
    def _delete_all_tags(page: Page):
        """Empty the registry from the manager, and return the row locator."""
        rows = page.locator('#event-tags-modal .tag-row')
        while count := rows.count():
            # Each delete swaps the list back in, so the next row's button is
            # a new node htmx has yet to take over.
            TestUtils.wait_for_htmx_bound(
                page, '#event-tags-modal .tag-row button[hx-post*="/tag/delete/"]'
            )
            rows.first.locator('button:has(.bi-trash-fill)').click()
            expect(rows).to_have_count(count - 1)
        return rows

    @staticmethod
    def _drag_row(page: Page, source, target):
        """Drag *source* onto *target*. Sortable.js tracks the pointer, so
        the move is played out in steps rather than jumped in one go."""
        source.hover()
        page.mouse.down()
        target_box = target.bounding_box()
        assert target_box is not None
        for ratio in (0.4, 0.7, 1.0):
            page.mouse.move(
                target_box['x'] + target_box['width'] / 2,
                target_box['y'] + target_box['height'] * (1 - ratio) / 2,
                steps=5,
            )
        page.mouse.up()

    def _create_tag(self, page: Page, name: str, color: str, add_another=False):
        add = '#event-tags-modal button[hx-post*="/tag/add-form"]'
        TestUtils.wait_for_htmx_bound(page, add)
        page.locator(add).click()
        expect(page.get_by_test_id('tag-name')).to_be_visible()
        TestUtils.fill_and_confirm(page.get_by_test_id('tag-name'), name)
        page.get_by_test_id('tag-color').fill(color)
        if add_another:
            page.locator('.dropdown-toggle-split').click()
            TestUtils.submit_modal(
                page,
                page.get_by_role('button', name='Create and add another'),
                '#tags-modal-form',
            )
            # Stays on an empty form rather than returning to the list.
            expect(page.get_by_test_id('tag-name')).to_have_value('')
        else:
            TestUtils.submit_modal(
                page, page.get_by_test_id('create-button'), '#tags-modal-form'
            )
            expect(page.locator('#event-tags-modal')).to_contain_text(name)

    @pytest.fixture()
    def two_tags(self, api_request_context: APIRequestContext):
        """The registry the drag test rearranges. The tags are made through
        the API: what is being tested is the dragging, not the form."""
        ids = []
        for name in (TAG_NAME, SECOND_TAG_NAME):
            response = api_request_context.post(
                '/tag/create',
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                data=TestUtils.prepare_form_data(
                    {'tag_name': name, 'tag_color': '#123456'}
                ),
            )
            TestUtils.check_api_response(response)
        with ConfigDatabase() as database:
            ids = [
                tag.id
                for tag in database.load_stored_tags()
                if tag.name in (TAG_NAME, SECOND_TAG_NAME)
            ]
        yield
        for tag_id in ids:
            api_request_context.post(f'/tag/delete/{tag_id}')

    def test_unsaved_event_edits_survive_the_tags_modal(
        self, page: Page, api_request_context: APIRequestContext
    ):
        """The tag manager is a separate modal, so the event form it was
        opened from is carried through and restored by Back."""
        modal = self._open_event_config_modal(page, EVENT_ID)
        TestUtils.fill_and_confirm(modal.get_by_test_id('location'), 'Unsaved Location')
        TestUtils.wait_for_htmx_idle(page)
        modal.locator('#tags-configure-button').click()
        expect(page.locator('#event-tags-modal')).to_be_visible()
        self._back_to_the_event_form(page)
        expect(page.get_by_test_id('location')).to_have_value('Unsaved Location')

    def test_new_tags_go_last_and_can_be_dragged(
        self, page: Page, api_request_context: APIRequestContext, two_tags: None
    ):
        """Tags are arranged by hand rather than sorted, so a new one lands
        at the end of the registry and dragging it moves it for good."""
        self._open_tags_modal(page, EVENT_ID)
        rows = page.locator('#event-tags-modal .tag-row')
        names = page.locator('#event-tags-modal .tag-row .badge')
        assert names.all_inner_texts() == [TAG_NAME, SECOND_TAG_NAME]

        self._drag_row(page, rows.nth(1), rows.nth(0))
        expect(rows).to_have_count(2)
        assert names.all_inner_texts() == [SECOND_TAG_NAME, TAG_NAME]

        # The order is the registry's, so it holds outside this modal.
        self._goto_event_list(page)
        # Each filter badge reads "<name>\n(<count>)".
        filtered = page.locator('.events-tag-filter .badge').all_inner_texts()
        assert [name.split('\n')[0] for name in filtered] == [SECOND_TAG_NAME, TAG_NAME]
