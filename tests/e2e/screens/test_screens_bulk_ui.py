import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTournament
from tests.test_config import ScreenType, TestUtils

EVENT_ID = 'screens-bulk-test-event'


@pytest.fixture(autouse=True)
def tournament(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    yield TestUtils.create_tournament(
        EVENT_ID,
        'Open',
        via_api_request_context=api_request_context,
    )
    TestUtils.delete_event(EVENT_ID, via_api_request_context=api_request_context)


def _create_check_in_screens(
    api_request_context: APIRequestContext, tournament: StoredTournament
) -> dict[str, str]:
    """Three check-in screens, one not accepting input, and a paged one; the
    collection item ids by name."""
    item_ids: dict[str, str] = {}
    for name, accepts_input in (('Hall', True), ('Lobby', False), ('Bar', True)):
        screen = TestUtils.create_screen(
            api_request_context,
            EVENT_ID,
            name,
            ScreenType.CHECK_IN,
            {
                'init_set_tournament_ids': [tournament.id],
                'accepts_input': accepts_input,
            },
        )
        item_ids[name] = str(screen.id)
    family = TestUtils.create_family(
        api_request_context, EVENT_ID, tournament, 'pages', ScreenType.CHECK_IN
    )
    item_ids['pages'] = f'family-{family.id}'
    return item_ids


def _select(page: Page, item_ids: list[str]):
    section = page.locator(f'#admin-screens-section-{ScreenType.CHECK_IN.value}')
    for item_id in item_ids:
        section.locator(f'.screens-bulk-select[value="{item_id}"]').check()
    return section


@pytest.mark.e2e
class TestScreensBulk:
    def test_only_the_changed_fields_are_applied_to_the_selected_screens(
        self,
        page: Page,
        api_request_context: APIRequestContext,
        tournament: StoredTournament,
    ):
        item_ids = _create_check_in_screens(api_request_context, tournament)
        projector = TestUtils.create_display_controller(
            api_request_context, EVENT_ID, 'Projector'
        )
        page.goto(f'/event/{EVENT_ID}/screens')
        section = _select(
            page, [item_ids['Hall'], item_ids['Lobby'], item_ids['pages']]
        )
        expect(
            section.get_by_test_id(f'screens-bulk-toolbar-{ScreenType.CHECK_IN.value}')
        ).to_contain_text('3 selected')
        section.get_by_test_id('screens-bulk-edit').click()

        form = page.locator('#modal-form')
        expect(
            form.locator('.screens-bulk-mixed [name="accepts_input"]')
        ).to_be_attached()
        TestUtils.wait_for_htmx_idle(page)
        TestUtils.fill_and_confirm(form.locator('[name="font_size"]'), '130')
        form.locator('select[name="display_controller_ids"]').evaluate(
            "(select, id) => $(select).val([id]).trigger('change')", str(projector.id)
        )
        TestUtils.submit_modal(page, page.get_by_test_id('screens-bulk-submit'))
        expect(form).to_have_count(0)
        expect(page.locator('#messages')).to_contain_text(
            '3 screens have been updated.'
        )

        with EventDatabase(EVENT_ID) as event_database:
            screens = {
                screen.name: screen for screen in event_database.load_stored_screens()
            }
            families = list(event_database.load_stored_families())
            controller = next(
                controller
                for controller in event_database.load_stored_display_controllers()
                if controller.id == projector.id
            )
        assert screens['Hall'].font_size == 130
        assert screens['Lobby'].font_size == 130
        assert families[0].font_size == 130
        assert screens['Bar'].font_size is None
        assert screens['Hall'].accepts_input
        assert not screens['Lobby'].accepts_input
        assert screens['Hall'].plugin_data == {}
        assert set(controller.item_screen_ids) == {
            screens['Hall'].id,
            screens['Lobby'].id,
        }
        assert controller.item_family_ids == [families[0].id]

    def test_a_selection_stays_within_one_screen_type(
        self,
        page: Page,
        api_request_context: APIRequestContext,
        tournament: StoredTournament,
    ):
        item_ids = _create_check_in_screens(api_request_context, tournament)
        TestUtils.create_screen(
            api_request_context,
            EVENT_ID,
            'Pairings',
            ScreenType.BOARDS,
            {'init_set_tournament_ids': [tournament.id]},
        )
        page.goto(f'/event/{EVENT_ID}/screens')
        check_in = _select(page, [item_ids['Hall'], item_ids['Bar']])
        boards = page.locator(f'#admin-screens-section-{ScreenType.BOARDS.value}')
        boards.locator('.screens-bulk-select').first.check()
        expect(check_in.locator('.screens-bulk-select:checked')).to_have_count(0)
        expect(
            check_in.get_by_test_id(f'screens-bulk-toolbar-{ScreenType.CHECK_IN.value}')
        ).to_be_hidden()

    def test_the_selected_screens_are_deleted(
        self,
        page: Page,
        api_request_context: APIRequestContext,
        tournament: StoredTournament,
    ):
        item_ids = _create_check_in_screens(api_request_context, tournament)
        page.goto(f'/event/{EVENT_ID}/screens')
        section = _select(page, [item_ids['Lobby'], item_ids['pages']])
        section.get_by_test_id('screens-bulk-delete').click()
        expect(page.get_by_test_id('screens-bulk-names')).to_contain_text('Lobby')
        TestUtils.submit_modal(page, page.get_by_test_id('screens-bulk-submit'))
        expect(page.locator('#messages')).to_contain_text(
            '2 screens have been deleted.'
        )

        with EventDatabase(EVENT_ID) as event_database:
            names = {screen.name for screen in event_database.load_stored_screens()}
            families = list(event_database.load_stored_families())
        assert names == {'Hall', 'Bar'}
        assert families == []
