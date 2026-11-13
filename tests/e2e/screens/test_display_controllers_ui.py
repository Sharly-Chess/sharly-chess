import re

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTournament
from tests.test_config import ScreenType, TestUtils

EVENT_ID = 'display-controller-test-event'
TOURNAMENT_NAME = 'Club tournament'


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
class TestDisplayControllers:
    def test_a_waiting_device_picks_up_the_first_screen_sent_to_it(
        self,
        page: Page,
        api_request_context: APIRequestContext,
        tournament: StoredTournament,
    ):
        controller = TestUtils.create_display_controller(
            api_request_context, EVENT_ID, 'Projector'
        )
        screen = TestUtils.create_screen(
            api_request_context,
            EVENT_ID,
            'Check-in',
            ScreenType.CHECK_IN,
            {'init_set_tournament_ids': [tournament.id]},
        )
        page.goto(f'/view/display-controller/{EVENT_ID}/{controller.id}')
        waiting = page.get_by_test_id('display-controller-waiting')
        expect(waiting).to_be_visible()

        response = api_request_context.patch(
            f'/display-controller-assign/{EVENT_ID}/{controller.id}'
            f'/screen/{screen.uniq_id}',
        )
        TestUtils.check_api_response(response)

        expect(waiting).to_have_count(0, timeout=20_000)

    def test_a_screen_designed_for_a_feed_shows_its_badge(
        self,
        page: Page,
        api_request_context: APIRequestContext,
    ):
        TestUtils.create_display_controller(api_request_context, EVENT_ID, 'iPad')
        projector = TestUtils.create_display_controller(
            api_request_context, EVENT_ID, 'Projector'
        )
        page.goto(f'/event/{EVENT_ID}/screens')
        page.get_by_role('button', name='Create a screen').click()
        page.get_by_test_id(f'create-screen-type-{ScreenType.CHECK_IN.value}').click()
        destinations = page.locator('#modal-form select[name="display_controller_ids"]')
        expect(destinations).to_be_attached()

        TestUtils.wait_for_htmx_idle(page)
        destinations.evaluate(
            "(select, id) => $(select).val([id]).trigger('change')", str(projector.id)
        )
        page.locator('#modal-form').evaluate('form => form.requestSubmit()')

        expect(destinations).to_have_count(0)
        row = page.get_by_test_id('screens-item').filter(has_text=TOURNAMENT_NAME)
        expect(row.locator('.badge', has_text='Projector')).to_be_visible()

        TestUtils.create_screen(
            api_request_context,
            EVENT_ID,
            'Results',
            ScreenType.RESULTS,
            {'display_controller_ids': [projector.id]},
        )
        page.goto(f'/event/{EVENT_ID}/display_controllers')
        row = page.locator(f'#collection-display-controllers-item-{projector.id}')
        row.get_by_role('button', name='Connect a device').click()
        expect(page.locator('.modal-dialog img').first).to_be_visible()
        page.get_by_role('button', name='Close').click()
        expect(page.locator('#modal-wrapper')).to_be_hidden()
        TestUtils.wait_for_htmx_idle(page)
        row.get_by_role('button', name='Edit the properties').last.click()
        expect(page.locator('#modal-form input[name="name"]')).to_have_value(
            'Projector'
        )
        page.get_by_role('button', name='Cancel').click()
        expect(row.get_by_test_id('screens-count')).to_contain_text('2')

    def test_a_submenu_stays_open_while_the_pointer_moves_slowly_into_it(
        self,
        page: Page,
        api_request_context: APIRequestContext,
        tournament: StoredTournament,
    ):
        controller = TestUtils.create_display_controller(
            api_request_context, EVENT_ID, 'Projector'
        )
        TestUtils.create_family(
            api_request_context,
            EVENT_ID,
            tournament,
            'boards',
            ScreenType.BOARDS,
            {'display_controller_ids': [controller.id]},
        )
        page.goto(f'/event/{EVENT_ID}/display_controllers')
        page.get_by_role('button', name='Send a screen to this channel.').click()
        item = page.locator('.dropdown-menu.show li.dropdown-submenu').first
        toggle = item.locator('.sc-submenu-toggle')
        toggle.hover()
        submenu = item.locator(':scope > .dropdown-menu')
        entry = submenu.locator('.dropdown-item').first
        expect(entry).to_be_visible()

        start = toggle.bounding_box()
        end = entry.bounding_box()
        assert start is not None and end is not None
        x, y = start['x'] + 10, start['y'] + start['height'] / 2
        to_x, to_y = end['x'] + end['width'] / 2, end['y'] + end['height'] / 2
        steps = 60
        for step in range(1, steps + 1):
            page.mouse.move(
                x + (to_x - x) * step / steps, y + (to_y - y) * step / steps
            )
            page.wait_for_timeout(16)
        expect(entry).to_be_visible()

    def test_tapping_a_menu_on_a_destination_keeps_the_device_on_it(
        self,
        page: Page,
        api_request_context: APIRequestContext,
        tournament: StoredTournament,
    ):
        api = api_request_context
        results = TestUtils.create_screen(api, EVENT_ID, 'Results', ScreenType.RESULTS)
        check_in = TestUtils.create_screen(
            api,
            EVENT_ID,
            'Check-in',
            ScreenType.CHECK_IN,
            {'init_set_tournament_ids': [tournament.id]},
        )
        controller = TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
        form_headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        TestUtils.check_api_response(
            api.post(
                f'/menu-create/{EVENT_ID}',
                headers=form_headers,
                data=TestUtils.prepare_form_data({'name': 'Tablets'}),
            )
        )
        with EventDatabase(EVENT_ID) as database:
            menu_id = next(iter(database.load_stored_menus())).id
        for screen in (results, check_in):
            TestUtils.check_api_response(
                api.post(
                    f'/menu-items/create/{EVENT_ID}/{menu_id}',
                    headers=form_headers,
                    data=TestUtils.prepare_form_data(
                        {'item_id': f'screen:{screen.id}'}
                    ),
                )
            )
        TestUtils.check_api_response(
            api.patch(
                f'/display-controller-assign/{EVENT_ID}/{controller.id}/menu/{menu_id}',
                headers=form_headers,
            )
        )

        url = f'/view/display-controller/{EVENT_ID}/{controller.id}'
        page.goto(url)
        page.locator('#screen-menu').get_by_text('Check-in').click()
        expect(page.locator('#user-screen-header')).to_have_attribute(
            'data-page-title', 'Check-in'
        )
        expect(page).to_have_url(re.compile(f'{url}/1$'))

        TestUtils.check_api_response(
            api.patch(
                f'/display-controller-assign/{EVENT_ID}/{controller.id}'
                f'/screen/{results.uniq_id}',
                headers=form_headers,
            )
        )
        expect(page.locator('#screen-menu')).to_have_count(0, timeout=20_000)
        expect(page.locator('#user-screen-header')).to_have_attribute(
            'data-page-title', 'Results'
        )

    def test_a_multi_screen_on_a_destination_cycles_through_its_pages(
        self,
        page: Page,
        api_request_context: APIRequestContext,
    ):
        api = api_request_context
        tournament = TestUtils.create_tournament(
            EVENT_ID,
            'Split tournament',
            json_file='test-screens',
            via_api_request_context=api,
        )
        family = TestUtils.create_family(
            api,
            EVENT_ID,
            tournament,
            'split-players',
            ScreenType.PLAYERS,
            {'parts': 2},
        )
        controller = TestUtils.create_display_controller(api, EVENT_ID, 'Projector')
        TestUtils.check_api_response(
            api.patch(
                f'/display-controller-assign/{EVENT_ID}/{controller.id}'
                f'/family/{family.uniq_id}',
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
            )
        )
        refresher = page.locator('.display-controller-refresher')
        url = f'/view/display-controller/{EVENT_ID}/{controller.id}'
        page.goto(url)
        showing = f'?showing=family:{family.id}'
        expect(refresher).to_have_attribute('hx-get', f'{url}/1{showing}')
        expect(refresher).to_have_attribute(
            'hx-get', f'{url}/2{showing}', timeout=20_000
        )

    def test_the_map_on_an_empty_tab_leads_to_the_other_tabs(self, page: Page):
        page.goto(f'/event/{EVENT_ID}/rotators')
        page.get_by_test_id('screens-map-displays').click()
        expect(page).to_have_url(re.compile(f'/event/{EVENT_ID}/display_controllers$'))
        expect(page.get_by_test_id('screens-map-displays')).to_have_attribute(
            'aria-current', 'page'
        )
