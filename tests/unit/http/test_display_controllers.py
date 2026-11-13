"""Display controllers: the devices of a venue and the screens set up for them."""

from collections.abc import Iterator
from typing import Any

import pytest
from AdvancedHTMLParser import AdvancedHTMLParser
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredDisplayController,
    StoredFamily,
    StoredMenu,
    StoredMenuItem,
    StoredScreen,
    StoredTournament,
)
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient

EVENT_ID = 'test-display-controllers-http'
TOURNAMENT_NAME = 'Club tournament'
FORM_HEADERS = {'Content-Type': 'application/x-www-form-urlencoded'}


@pytest.fixture
def tournament() -> Iterator[StoredTournament]:
    TestUtils.create_event(EVENT_ID)
    yield TestUtils.create_tournament(
        EVENT_ID, TOURNAMENT_NAME, json_file='test-screens'
    )
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def stored_controller(controller_id: int | None) -> StoredDisplayController:
    assert controller_id is not None
    with EventDatabase(EVENT_ID) as database:
        stored = database.get_stored_display_controller(controller_id)
    assert stored is not None
    return stored


def check_in_screen(
    api: ApiClient, tournament: StoredTournament, name: str | None, **overrides: object
) -> StoredScreen:
    if name:
        return TestUtils.create_screen(
            api,
            EVENT_ID,
            name,
            ScreenType.CHECK_IN,
            {'init_set_tournament_ids': [tournament.id], **overrides},
        )
    response = api.post(
        f'/screen-create/{EVENT_ID}/{ScreenType.CHECK_IN.value}',
        headers=FORM_HEADERS,
        data=TestUtils.prepare_form_data(
            {
                'init_set_tournament_ids': [tournament.id],
                'public': True,
                'message_text_checkbox': True,
                **overrides,
            }
        ),
    )
    TestUtils.check_api_response(response)
    with EventDatabase(EVENT_ID) as database:
        return max(database.load_stored_screens(), key=lambda screen: screen.id or 0)


def screen_name(screen_id: int | None) -> str:
    assert screen_id is not None
    EventLoader.unload_event(EVENT_ID)
    event = EventLoader().load_event(EVENT_ID)
    return event.basic_screens_by_id[screen_id].name


def test_a_screen_can_be_set_up_for_several_controllers(
    api: ApiClient, tournament: StoredTournament
) -> None:
    ipad = TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    projector = TestUtils.create_display_controller(api, EVENT_ID, 'Projector')
    assert ipad.id is not None and projector.id is not None
    shared = check_in_screen(
        api, tournament, None, display_controller_ids=[ipad.id, projector.id]
    )
    own = check_in_screen(api, tournament, None, display_controller_ids=[ipad.id])

    assert set(stored_controller(ipad.id).item_screen_ids) == {shared.id, own.id}
    assert stored_controller(projector.id).item_screen_ids == [shared.id]


def test_a_feed_does_not_change_the_name_of_a_screen(
    api: ApiClient, tournament: StoredTournament
) -> None:
    ipad = TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    projector = TestUtils.create_display_controller(api, EVENT_ID, 'Projector')
    assert ipad.id is not None and projector.id is not None
    one = check_in_screen(api, tournament, None, display_controller_ids=[ipad.id])
    both = check_in_screen(
        api, tournament, None, display_controller_ids=[ipad.id, projector.id]
    )
    named = check_in_screen(
        api, tournament, 'Front desk', display_controller_ids=[ipad.id]
    )

    assert screen_name(one.id) == TOURNAMENT_NAME
    assert screen_name(both.id) == TOURNAMENT_NAME
    assert screen_name(named.id) == 'Front desk'


def test_an_unknown_destination_is_refused(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    response = http.post(
        f'/screen-create/{EVENT_ID}/{ScreenType.CHECK_IN.value}',
        headers=FORM_HEADERS,
        content=TestUtils.prepare_form_data(
            {
                'init_set_tournament_ids': [tournament.id],
                'public': True,
                'display_controller_ids': [999],
            }
        ),
    )
    assert response.status_code == 200
    assert 'Invalid value.' in response.text
    with EventDatabase(EVENT_ID) as database:
        assert not list(database.load_stored_screens())


def test_removing_a_screen_or_a_controller_removes_only_the_link(
    api: ApiClient, tournament: StoredTournament
) -> None:
    ipad = TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    projector = TestUtils.create_display_controller(api, EVENT_ID, 'Projector')
    assert ipad.id is not None and projector.id is not None
    gone = check_in_screen(api, tournament, None, display_controller_ids=[ipad.id])
    kept = check_in_screen(
        api, tournament, 'Kept', display_controller_ids=[ipad.id, projector.id]
    )

    TestUtils.check_api_response(
        api.delete(f'/screen-delete/{EVENT_ID}/{gone.id}', headers=FORM_HEADERS)
    )
    assert stored_controller(ipad.id).item_screen_ids == [kept.id]

    TestUtils.check_api_response(
        api.delete(
            f'/display-controller-delete/{EVENT_ID}/{ipad.id}', headers=FORM_HEADERS
        )
    )
    assert stored_controller(projector.id).item_screen_ids == [kept.id]
    assert screen_name(kept.id) == 'Kept'


def test_the_row_counts_the_screens_and_the_details_name_them(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    first = check_in_screen(api, tournament, 'First screen')
    second = check_in_screen(api, tournament, 'Second screen')
    controller = TestUtils.create_display_controller(
        api,
        EVENT_ID,
        'Projector',
        {'item_ids': [f'screen:{first.id}', f'screen:{second.id}']},
    )

    response = http.get(
        f'/event/{EVENT_ID}/display_controllers', params={'collection_view': 'list'}
    )

    assert response.status_code == 200
    parser = AdvancedHTMLParser()
    parser.parseStr(response.text)
    count = parser.getElementsByAttr('data-testid', 'screens-count')[0]
    assert count.textContent.strip() == '2'
    details = parser.getElementById(
        f'collection-display-controllers-details-{controller.id}'
    ).getHTML()
    assert 'First screen' in details
    assert 'Second screen' in details


def test_the_controller_modal_edits_its_list(
    api: ApiClient, tournament: StoredTournament
) -> None:
    screen = check_in_screen(api, tournament, 'Check-in')
    controller = TestUtils.create_display_controller(
        api,
        EVENT_ID,
        'Projector',
        {'item_ids': [f'screen:{screen.id}']},
    )
    assert stored_controller(controller.id).item_screen_ids == [screen.id]


def test_a_multi_screen_can_be_set_up_for_a_controller(
    api: ApiClient, tournament: StoredTournament
) -> None:
    projector = TestUtils.create_display_controller(api, EVENT_ID, 'Projector')
    assert projector.id is not None
    family = TestUtils.create_family(
        api,
        EVENT_ID,
        tournament,
        'test-display-controllers-family',
        ScreenType.BOARDS,
        {'display_controller_ids': [projector.id]},
    )
    assert stored_controller(projector.id).item_family_ids == [family.id]


def family_with_pages(
    api: ApiClient, tournament: StoredTournament, screen_type: ScreenType
) -> StoredFamily:
    return TestUtils.create_family(
        api,
        EVENT_ID,
        tournament,
        'test-display-controllers-pages',
        screen_type,
        {'parts': 2},
    )


def test_a_controller_cycles_through_the_pages_of_a_multi_screen(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    family = family_with_pages(api, tournament, ScreenType.BOARDS)
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'Projector')
    TestUtils.check_api_response(
        api.patch(
            f'/display-controller-assign/{EVENT_ID}/{controller.id}'
            f'/family/{family.uniq_id}',
            headers=FORM_HEADERS,
        )
    )
    assert stored_controller(controller.id).family_id == family.id

    page = http.get(f'/view/display-controller/{EVENT_ID}/{controller.id}')
    assert page.status_code == 200
    assert 'display-controller-waiting' not in page.text
    assert f'/view/display-controller/{EVENT_ID}/{controller.id}/1' in page.text
    assert (
        http.get(f'/view/display-controller/{EVENT_ID}/{controller.id}/1').status_code
        == 200
    )


def test_sending_a_screen_replaces_a_multi_screen(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    family = family_with_pages(api, tournament, ScreenType.BOARDS)
    screen = TestUtils.create_screen(api, EVENT_ID, 'Results', ScreenType.RESULTS)
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'Projector')
    for kind, uniq_id in (('family', family.uniq_id), ('screen', screen.uniq_id)):
        TestUtils.check_api_response(
            api.patch(
                f'/display-controller-assign/{EVENT_ID}/{controller.id}'
                f'/{kind}/{uniq_id}',
                headers=FORM_HEADERS,
            )
        )
    stored = stored_controller(controller.id)
    assert (stored.screen_id, stored.family_id) == (screen.id, None)


def test_a_check_in_multi_screen_is_sent_a_page_at_a_time(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    family = family_with_pages(api, tournament, ScreenType.CHECK_IN)
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    http.patch(
        f'/display-controller-assign/{EVENT_ID}/{controller.id}'
        f'/family/{family.uniq_id}',
    )
    assert stored_controller(controller.id).family_id is None

    modal = http.get(f'/family-modal/update/{EVENT_ID}/{family.id}')
    assert 'display_controller_ids' in modal.text
    TestUtils.check_api_response(
        api.patch(
            f'/display-controller-update/{EVENT_ID}/{controller.id}',
            headers=FORM_HEADERS,
            data=TestUtils.prepare_form_data(
                {'name': 'iPad', 'public': True, 'item_ids': [f'family:{family.id}']}
            ),
        )
    )
    assert stored_controller(controller.id).item_family_ids == [family.id]

    tab = http.get(f'/event/{EVENT_ID}/display_controllers').text
    assert f'/family-page/{family.uniq_id}:001' in tab
    assert f'/family/{family.uniq_id}"' not in tab


def send_page(api: ApiClient, controller_id: int | None, page_uniq_id: str) -> None:
    TestUtils.check_api_response(
        api.patch(
            f'/display-controller-assign/{EVENT_ID}/{controller_id}'
            f'/family-page/{page_uniq_id}',
            headers=FORM_HEADERS,
        )
    )


def test_a_controller_can_be_held_on_one_page(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    family = family_with_pages(api, tournament, ScreenType.BOARDS)
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'Projector')
    send_page(api, controller.id, f'{family.uniq_id}:002')
    stored = stored_controller(controller.id)
    assert (stored.family_id, stored.family_page) == (family.id, 2)

    page = http.get(f'/view/display-controller/{EVENT_ID}/{controller.id}')
    assert page.status_code == 200
    assert 'display-controller-waiting' not in page.text
    assert f'/view/display-controller/{EVENT_ID}/{controller.id}/1' not in page.text

    tab = http.get(f'/event/{EVENT_ID}/screens').text
    assert 'Send this page to a channel.' in tab
    assert 'already showing it' in tab


def test_sending_the_whole_multi_screen_lets_the_controller_cycle_again(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    family = family_with_pages(api, tournament, ScreenType.BOARDS)
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'Projector')
    send_page(api, controller.id, f'{family.uniq_id}:001')
    TestUtils.check_api_response(
        api.patch(
            f'/display-controller-assign/{EVENT_ID}/{controller.id}'
            f'/family/{family.uniq_id}',
            headers=FORM_HEADERS,
        )
    )
    stored = stored_controller(controller.id)
    assert (stored.family_id, stored.family_page) == (family.id, None)


def test_editing_a_controller_keeps_its_page(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    family = family_with_pages(api, tournament, ScreenType.BOARDS)
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'Projector')
    send_page(api, controller.id, f'{family.uniq_id}:002')
    TestUtils.check_api_response(
        api.patch(
            f'/display-controller-update/{EVENT_ID}/{controller.id}',
            headers=FORM_HEADERS,
            data=TestUtils.prepare_form_data({'name': 'Big screen', 'public': True}),
        )
    )
    stored = stored_controller(controller.id)
    assert (stored.name, stored.family_page) == ('Big screen', 2)


def test_a_page_of_a_check_in_multi_screen_can_be_sent(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    family = family_with_pages(api, tournament, ScreenType.CHECK_IN)
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    send_page(api, controller.id, f'{family.uniq_id}:001')
    assert stored_controller(controller.id).family_page == 1

    page = http.get(f'/view/display-controller/{EVENT_ID}/{controller.id}')
    assert page.status_code == 200
    assert 'display-controller-waiting' not in page.text


def test_a_controller_on_a_page_that_no_longer_exists_waits(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    family = family_with_pages(api, tournament, ScreenType.BOARDS)
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'Projector')
    send_page(api, controller.id, f'{family.uniq_id}:002')
    stored = stored_controller(controller.id)
    stored.family_page = 9
    with EventDatabase(EVENT_ID, True) as database:
        database.update_stored_display_controller(stored)
    EventLoader.unload_event(EVENT_ID)

    page = http.get(f'/view/display-controller/{EVENT_ID}/{controller.id}')
    assert page.status_code == 200
    assert 'display-controller-waiting' in page.text


def test_deleting_a_multi_screen_sends_its_controller_back_to_waiting(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    family = family_with_pages(api, tournament, ScreenType.BOARDS)
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'Projector')
    TestUtils.check_api_response(
        api.patch(
            f'/display-controller-assign/{EVENT_ID}/{controller.id}'
            f'/family/{family.uniq_id}',
            headers=FORM_HEADERS,
        )
    )
    assert family.id is not None
    TestUtils.delete_family(api, EVENT_ID, family.id)

    page = http.get(f'/view/display-controller/{EVENT_ID}/{controller.id}')
    assert page.status_code == 200
    assert 'display-controller-waiting' in page.text


def menu_of(screens: list[StoredScreen], name: str = 'Tablets') -> int:
    with EventDatabase(EVENT_ID, True) as database:
        menu_id = database.add_stored_menu(StoredMenu(id=None, name=name))
        for index, screen in enumerate(screens):
            database.add_stored_menu_item(
                StoredMenuItem(
                    id=None, menu_id=menu_id, screen_id=screen.id, index=index
                )
            )
    EventLoader.unload_event(EVENT_ID)
    return menu_id


def send_menu(api: ApiClient, controller_id: int | None, menu_id: int) -> None:
    TestUtils.check_api_response(
        api.patch(
            f'/display-controller-assign/{EVENT_ID}/{controller_id}/menu/{menu_id}',
            headers=FORM_HEADERS,
        )
    )


def test_a_menu_on_a_controller_stays_on_the_controller(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    results = TestUtils.create_screen(api, EVENT_ID, 'Results', ScreenType.RESULTS)
    check_in = check_in_screen(api, tournament, 'Check-in')
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    send_menu(api, controller.id, menu_of([results, check_in]))
    url = f'/view/display-controller/{EVENT_ID}/{controller.id}'

    first = http.get(url)
    assert first.status_code == 200
    assert 'id="screen-menu"' in first.text
    assert f'{url}/1' in first.text
    assert f'/view/screen/{EVENT_ID}/' not in first.text

    second = http.get(f'{url}/1')
    assert second.status_code == 200
    assert 'data-page-title="Check-in"' in second.text
    assert f'{url}/0' in second.text


def test_a_screen_opened_directly_has_no_menu(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    results = TestUtils.create_screen(api, EVENT_ID, 'Results', ScreenType.RESULTS)
    check_in = check_in_screen(api, tournament, 'Check-in')
    menu_of([results, check_in])
    page = http.get(f'/view/screen/{EVENT_ID}/{results.uniq_id}')
    assert page.status_code == 200
    assert 'id="screen-menu"' not in page.text


def test_a_menu_has_its_own_address(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    results = TestUtils.create_screen(api, EVENT_ID, 'Results', ScreenType.RESULTS)
    check_in = check_in_screen(api, tournament, 'Check-in')
    menu_id = menu_of([results, check_in])
    url = f'/view/menu/{EVENT_ID}/{menu_id}'

    first = http.get(url)
    assert first.status_code == 200
    assert 'id="screen-menu"' in first.text
    assert 'data-page-title="Results"' in first.text
    assert f'{url}/1' in first.text

    second = http.get(f'{url}/1')
    assert 'data-page-title="Check-in"' in second.text
    assert f'{url}/0' in second.text


def test_the_same_screen_can_be_in_several_menus(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    shared = TestUtils.create_screen(api, EVENT_ID, 'Shared', ScreenType.RESULTS)
    other = TestUtils.create_screen(api, EVENT_ID, 'Other', ScreenType.RESULTS)
    third = TestUtils.create_screen(api, EVENT_ID, 'Third', ScreenType.RESULTS)
    first_menu = menu_of([shared, other], 'First')
    second_menu = menu_of([shared, third], 'Second')

    first = http.get(f'/view/menu/{EVENT_ID}/{first_menu}').text
    second = http.get(f'/view/menu/{EVENT_ID}/{second_menu}').text

    assert '>Other<' in first and '>Third<' not in first
    assert '>Third<' in second and '>Other<' not in second

    modal = http.get(f'/menu-items-modal/{EVENT_ID}/{second_menu}').text
    assert 'already belongs to a menu' not in modal
    assert 'This screen already belongs to this menu.' in modal


def test_entering_on_a_menu_opened_directly_stays_on_the_menu(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    results = TestUtils.create_screen(api, EVENT_ID, 'Results', ScreenType.RESULTS)
    check_in = check_in_screen(api, tournament, 'Check-in')
    menu_id = menu_of([results, check_in])
    assert f'?menu_id={menu_id}' in http.get(f'/view/menu/{EVENT_ID}/{menu_id}/1').text

    event = EventLoader().load_event(EVENT_ID)
    assert tournament.id is not None
    player = next(iter(event.tournaments_by_id[tournament.id].tournament_players))
    response = http.patch(
        f'/view/toggle-check-in/1/{EVENT_ID}/{check_in.uniq_id}'
        f'/{tournament.id}/{player.id}?menu_id={menu_id}'
    )
    assert response.status_code == 200
    assert 'id="screen-menu"' in response.text
    assert f'/view/menu/{EVENT_ID}/{menu_id}/1' in response.text


def test_a_device_starts_on_the_first_page_of_what_it_is_sent_next(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    first = TestUtils.create_screen(api, EVENT_ID, 'First', ScreenType.RESULTS)
    second = TestUtils.create_screen(api, EVENT_ID, 'Second', ScreenType.RESULTS)
    third = TestUtils.create_screen(api, EVENT_ID, 'Third', ScreenType.RESULTS)
    fourth = TestUtils.create_screen(api, EVENT_ID, 'Fourth', ScreenType.RESULTS)
    menu = menu_of([first, second], 'First menu')
    other_menu = menu_of([third, fourth], 'Second menu')
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    url = f'/view/display-controller/{EVENT_ID}/{controller.id}'

    send_menu(api, controller.id, menu)
    page = http.get(f'{url}/1')
    assert 'data-page-title="Second"' in page.text
    assert f'{url}/1?showing=menu:{menu}' in page.text

    same = http.get(f'{url}/1?showing=menu:{menu}')
    assert 'data-page-title="Second"' in same.text

    send_menu(api, controller.id, other_menu)
    switched = http.get(f'{url}/1?showing=menu:{menu}')
    assert 'data-page-title="Third"' in switched.text


def test_a_screen_on_a_destination_has_no_exit_button(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    screen = TestUtils.create_screen(api, EVENT_ID, 'Results', ScreenType.RESULTS)
    controller = TestUtils.create_display_controller(
        api, EVENT_ID, 'Projector', screen_uniq_id=screen.uniq_id
    )
    assert (
        'screen-exit-button'
        in http.get(f'/view/screen/{EVENT_ID}/{screen.uniq_id}').text
    )
    assert (
        'screen-exit-button'
        not in http.get(f'/view/display-controller/{EVENT_ID}/{controller.id}').text
    )


def test_entering_on_a_menu_page_acts_on_that_page(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    results = TestUtils.create_screen(api, EVENT_ID, 'Results', ScreenType.RESULTS)
    check_in = check_in_screen(api, tournament, 'Check-in')
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    send_menu(api, controller.id, menu_of([results, check_in]))
    url = f'/view/display-controller/{EVENT_ID}/{controller.id}'

    assert '?screen_index=1' in http.get(f'{url}/1').text

    event = EventLoader().load_event(EVENT_ID)
    assert tournament.id is not None
    player = next(iter(event.tournaments_by_id[tournament.id].tournament_players))
    response = http.patch(
        f'/view/toggle-check-in/0/{EVENT_ID}/{controller.id}'
        f'/{tournament.id}/{player.id}?screen_index=1'
    )
    assert response.status_code == 200
    assert 'data-page-title="Check-in"' in response.text
    assert f'{url}/1' in response.text


def test_a_menu_with_nothing_to_show_leaves_its_controller_waiting(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    menu_id = menu_of([])
    send_menu(api, controller.id, menu_id)
    url = f'/view/display-controller/{EVENT_ID}/{controller.id}'
    assert 'display-controller-waiting' in http.get(url).text


def test_deleting_a_menu_clears_its_controller_and_its_list(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    screen = TestUtils.create_screen(api, EVENT_ID, 'Results', ScreenType.RESULTS)
    menu_id = menu_of([screen])
    controller = TestUtils.create_display_controller(
        api, EVENT_ID, 'iPad', {'item_ids': [f'menu:{menu_id}']}
    )
    assert stored_controller(controller.id).item_menu_ids == [menu_id]
    send_menu(api, controller.id, menu_id)
    assert stored_controller(controller.id).menu_id == menu_id

    TestUtils.check_api_response(
        api.delete(f'/menu-delete/{EVENT_ID}/{menu_id}', headers=FORM_HEADERS)
    )
    stored = stored_controller(controller.id)
    assert (stored.menu_id, stored.item_menu_ids) == (None, [])


def test_the_menu_modal_sets_its_destinations(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    menu_id = menu_of([])
    TestUtils.check_api_response(
        api.patch(
            f'/menu-update/{EVENT_ID}/{menu_id}',
            headers=FORM_HEADERS,
            data=TestUtils.prepare_form_data(
                {'name': 'Tablets', 'display_controller_ids': [controller.id]}
            ),
        )
    )
    assert stored_controller(controller.id).item_menu_ids == [menu_id]
    modal = http.get(f'/menu-modal/update/{EVENT_ID}/{menu_id}')
    assert 'display_controller_ids' in modal.text


@pytest.mark.parametrize(
    ('tab', 'nodes'),
    [
        ('display_controllers', ['displays']),
        ('screens', ['screens']),
        ('rotators', ['rotators']),
        ('menus', ['menus']),
        ('timers', ['timers']),
    ],
)
def test_an_empty_tab_shows_where_it_sits_on_the_map(
    http: TestClient, tab: str, nodes: list[str]
) -> None:
    TestUtils.create_event(EVENT_ID)
    try:
        response = http.get(f'/event/{EVENT_ID}/{tab}')
    finally:
        EventLoader.unload_event(EVENT_ID)
        TestUtils.delete_event(EVENT_ID)
    assert response.status_code == 200
    parser = AdvancedHTMLParser()
    parser.parseStr(response.text)
    current = [
        element.getAttribute('data-testid')
        for element in parser.getElementsByAttr('aria-current', 'page')
        if element.getAttribute('data-testid', '').startswith('screens-map-')
    ]
    assert current == [f'screens-map-{node}' for node in nodes]


def test_the_map_gives_way_once_a_tab_has_content(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    TestUtils.create_rotator(api, EVENT_ID, 'Lobby')
    response = http.get(f'/event/{EVENT_ID}/rotators')
    assert 'screens-map-rotators' not in response.text
    assert '/screens-map-modal/' in response.text

    modal = http.get(f'/screens-map-modal/{EVENT_ID}?active=rotators')
    assert modal.status_code == 200
    assert 'screens-map-rotators' in modal.text


def test_the_side_menu_has_a_single_display_entry(
    http: TestClient, tournament: StoredTournament
) -> None:
    text = http.get(f'/event/{EVENT_ID}/screens').text
    assert 'data-testid="nav-admin-event-views-link"' in text
    for tab in ('display-controllers', 'screens', 'rotators', 'menus', 'timers'):
        assert f'data-testid="nav-admin-event-{tab}-tab"' not in text
    positions = [
        text.index(f'data-testid="display-switcher-{key}"')
        for key in ('displays', 'screens', 'rotators', 'menus', 'timers')
    ]
    assert positions == sorted(positions)


def test_the_screens_tab_lists_paged_screens_with_their_pages(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    single = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Board list',
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id]},
    )
    family = TestUtils.create_family(
        api,
        EVENT_ID,
        tournament,
        'test-display-controllers-pages',
        ScreenType.BOARDS,
        {'parts': 2},
    )
    text = http.get(
        f'/event/{EVENT_ID}/screens', params={'collection_view': 'list'}
    ).text
    assert f'collection-screens-item-{single.id}"' in text
    assert f'collection-screens-item-family-{family.id}"' in text
    assert text.count('data-testid="paged-screen-page"') == 2
    assert 'show-family-screens' not in text

    redirected = http.get(f'/event/{EVENT_ID}/families', follow_redirects=False)
    assert redirected.headers['location'] == f'/event/{EVENT_ID}/screens'


def test_a_new_screen_starts_with_a_set_for_each_tournament_chosen(
    api: ApiClient, tournament: StoredTournament
) -> None:
    other = TestUtils.create_tournament(EVENT_ID, 'Open B', json_file='test-screens')
    screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Both opens',
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id, other.id]},
    )
    with EventDatabase(EVENT_ID) as database:
        stored = next(
            stored
            for stored in database.load_stored_screens()
            if stored.id == screen.id
        )
    assert [screen_set.tournament_id for screen_set in stored.stored_screen_sets] == [
        tournament.id,
        other.id,
    ]


def test_a_new_screen_needs_a_tournament(
    http: TestClient, tournament: StoredTournament
) -> None:
    response = http.post(
        f'/screen-create/{EVENT_ID}/{ScreenType.BOARDS.value}',
        headers=FORM_HEADERS,
        content=TestUtils.prepare_form_data({'name': 'Nothing', 'public': True}),
    )
    assert 'Please choose the tournaments.' in response.text
    with EventDatabase(EVENT_ID) as database:
        assert not list(database.load_stored_screens())


@pytest.mark.parametrize(
    ('url', 'switch_expected'),
    [
        (f'/screen-modal/create/{EVENT_ID}/{ScreenType.BOARDS.value}', True),
        (f'/family-modal/create/{EVENT_ID}/{ScreenType.BOARDS.value}', True),
        (f'/screen-modal/create/{EVENT_ID}/{ScreenType.RESULTS.value}', False),
    ],
)
def test_creating_a_screen_offers_one_or_several_pages_at_the_top(
    http: TestClient, tournament: StoredTournament, url: str, switch_expected: bool
) -> None:
    modal = http.get(url).text
    assert ('data-testid="screen-kind-switch"' in modal) is switch_expected
    menu = http.get(f'/event/{EVENT_ID}/screens').text
    assert 'Over several pages' not in menu


def selected_destinations(html: str) -> list[str]:
    """The feeds selected in the Designed for field of a modal."""
    parser = AdvancedHTMLParser()
    parser.parseStr(html)
    return [
        option.getAttribute('value')
        for option in parser.getElementsByTagName('option')
        if option.hasAttribute('selected')
        and option.parentNode.getAttribute('name') == 'display_controller_ids'
    ]


def test_a_duplicated_screen_keeps_its_destinations_but_not_its_name(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    ipad = TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    assert ipad.id is not None
    screen = check_in_screen(api, tournament, None, display_controller_ids=[ipad.id])

    response = http.get(f'/screen-modal/clone/{EVENT_ID}/{screen.id}')

    assert response.status_code == 200
    assert selected_destinations(response.text) == [str(ipad.id)]
    parser = AdvancedHTMLParser()
    parser.parseStr(response.text)
    name = parser.getElementsByName('name')[0]
    assert not name.getAttribute('value')


@pytest.mark.parametrize('kind', ['family', 'rotator', 'menu'])
def test_a_duplicate_keeps_the_destinations_of_the_original(
    http: TestClient, api: ApiClient, tournament: StoredTournament, kind: str
) -> None:
    ipad = TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    assert ipad.id is not None
    overrides: dict[str, Any] = {'display_controller_ids': [ipad.id]}
    match kind:
        case 'family':
            family = TestUtils.create_family(
                api,
                EVENT_ID,
                tournament,
                'test-display-controllers-pages',
                ScreenType.RANKING,
                overrides,
            )
            url = f'/family-modal/clone/{EVENT_ID}/{family.id}'
        case 'rotator':
            rotator_id = TestUtils.create_rotator(
                api, EVENT_ID, 'Lobby', overrides=overrides
            )
            url = f'/rotator-modal/clone/{EVENT_ID}/{rotator_id}'
        case _:
            TestUtils.check_api_response(
                api.post(
                    f'/menu-create/{EVENT_ID}',
                    headers=FORM_HEADERS,
                    data=TestUtils.prepare_form_data({'name': 'Tablets'} | overrides),
                )
            )
            with EventDatabase(EVENT_ID) as database:
                menu_id = next(iter(database.load_stored_menus())).id
            url = f'/menu-modal/clone/{EVENT_ID}/{menu_id}'

    response = http.get(url)

    assert response.status_code == 200
    assert selected_destinations(response.text) == [str(ipad.id)]


def test_a_rotator_can_be_set_up_for_several_controllers(
    api: ApiClient, tournament: StoredTournament
) -> None:
    ipad = TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    projector = TestUtils.create_display_controller(api, EVENT_ID, 'Projector')
    assert ipad.id is not None and projector.id is not None
    rotator_id = TestUtils.create_rotator(
        api,
        EVENT_ID,
        'Lobby',
        overrides={'display_controller_ids': [ipad.id, projector.id]},
    )
    assert stored_controller(ipad.id).item_rotator_ids == [rotator_id]
    assert stored_controller(projector.id).item_rotator_ids == [rotator_id]

    TestUtils.check_api_response(
        api.patch(
            f'/rotator-update/{EVENT_ID}/{rotator_id}',
            headers=FORM_HEADERS,
            data=TestUtils.prepare_form_data(
                {
                    'name': 'Lobby',
                    'public': True,
                    'display_controller_ids': [projector.id],
                }
            ),
        )
    )
    assert stored_controller(ipad.id).item_rotator_ids == []
    assert stored_controller(projector.id).item_rotator_ids == [rotator_id]

    TestUtils.delete_rotator(api, EVENT_ID, rotator_id)
    assert stored_controller(projector.id).item_rotator_ids == []


def test_the_controller_modal_sets_up_rotators(
    api: ApiClient, tournament: StoredTournament
) -> None:
    rotator_id = TestUtils.create_rotator(api, EVENT_ID, 'Lobby')
    controller = TestUtils.create_display_controller(
        api, EVENT_ID, 'Projector', {'item_ids': [f'rotator:{rotator_id}']}
    )
    assert stored_controller(controller.id).item_rotator_ids == [rotator_id]


def test_the_rotator_modal_shows_its_destinations(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'Projector')
    assert controller.id is not None
    rotator_id = TestUtils.create_rotator(
        api, EVENT_ID, 'Lobby', overrides={'display_controller_ids': [controller.id]}
    )

    response = http.get(f'/rotator-modal/update/{EVENT_ID}/{rotator_id}')

    assert response.status_code == 200
    parser = AdvancedHTMLParser()
    parser.parseStr(response.text)
    selected = [
        option.getAttribute('value')
        for option in parser.getElementsByTagName('option')
        if option.hasAttribute('selected')
    ]
    assert str(controller.id) in selected


@pytest.mark.parametrize('with_destination', [True, False])
def test_the_modals_offer_destinations_once_a_controller_exists(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    with_destination: bool,
) -> None:
    if with_destination:
        TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    response = http.get(f'/screen-modal/create/{EVENT_ID}/{ScreenType.CHECK_IN.value}')
    assert response.status_code == 200
    assert ('display_controller_ids' in response.text) is with_destination


def test_the_connect_modal_opens(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    response = http.get(f'/display-controller-connect-modal/{EVENT_ID}/{controller.id}')
    assert response.status_code == 200
    assert 'Connect a device' in response.text


def test_an_empty_controller_waits_for_a_screen(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    response = http.get(f'/view/display-controller/{EVENT_ID}/{controller.id}')
    assert response.status_code == 200
    assert 'display-controller-waiting' in response.text
    assert 'iPad' in response.text


def test_a_controller_whose_screen_was_deleted_goes_back_to_waiting(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Check-in',
        ScreenType.CHECK_IN,
        {'init_set_tournament_ids': [tournament.id]},
    )
    controller = TestUtils.create_display_controller(
        api, EVENT_ID, 'iPad', screen_uniq_id=screen.uniq_id
    )
    url = f'/view/display-controller/{EVENT_ID}/{controller.id}'
    assert 'display-controller-waiting' not in http.get(url).text

    deleted = api.delete(f'/screen-delete/{EVENT_ID}/{screen.id}', headers=FORM_HEADERS)
    TestUtils.check_api_response(deleted)

    response = http.get(url)
    assert response.status_code == 200
    assert 'display-controller-waiting' in response.text


def test_editing_a_controller_keeps_what_it_is_showing(
    api: ApiClient, tournament: StoredTournament
) -> None:
    screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Check-in',
        ScreenType.CHECK_IN,
        {'init_set_tournament_ids': [tournament.id]},
    )
    controller = TestUtils.create_display_controller(
        api, EVENT_ID, 'iPad', screen_uniq_id=screen.uniq_id
    )
    response = api.patch(
        f'/display-controller-update/{EVENT_ID}/{controller.id}',
        headers=FORM_HEADERS,
        data=TestUtils.prepare_form_data({'name': 'Front desk', 'public': True}),
    )
    TestUtils.check_api_response(response)

    updated = stored_controller(controller.id)
    assert updated.name == 'Front desk'
    assert updated.screen_id == screen.id


def test_the_feeds_tab_can_preview_what_each_feed_shows(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'Projector')
    text = http.get(
        f'/event/{EVENT_ID}/display_controllers', params={'collection_view': 'preview'}
    ).text
    assert 'data-testid="display-controllers-previews"' in text
    assert f'src="/view/display-controller/{EVENT_ID}/{controller.id}"' in text


def test_screens_and_rotators_can_be_previewed(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    screen = check_in_screen(api, tournament, 'Check-in')
    family = family_with_pages(api, tournament, ScreenType.BOARDS)
    TestUtils.create_rotator(api, EVENT_ID, 'Lobby')
    screens = http.get(
        f'/event/{EVENT_ID}/screens', params={'collection_view': 'preview'}
    ).text
    assert f'src="/view/screen/{EVENT_ID}/{screen.uniq_id}"' in screens
    assert f'src="/view/screen/{EVENT_ID}/{family.uniq_id}:001"' in screens
    rotators = http.get(
        f'/event/{EVENT_ID}/rotators', params={'collection_view': 'preview'}
    ).text
    assert 'data-testid="rotators-previews"' in rotators


def test_menus_and_timers_have_no_preview(
    http: TestClient, tournament: StoredTournament
) -> None:
    for tab in ('menus', 'timers'):
        text = http.get(
            f'/event/{EVENT_ID}/{tab}', params={'collection_view': 'preview'}
        ).text
        assert 'Preview view' not in text
        assert '-previews"' not in text


def test_the_display_tabs_switch_from_the_top_of_the_page(
    http: TestClient, tournament: StoredTournament
) -> None:
    text = http.get(f'/event/{EVENT_ID}/rotators').text
    parser = AdvancedHTMLParser()
    parser.parseStr(text)
    assert parser.getElementsByAttr('data-testid', 'display-switcher')
    pressed = [
        button.getAttribute('data-map-key')
        for button in parser.getElementsByAttr('aria-pressed', 'true')
        if button.getAttribute('data-map-key')
    ]
    assert pressed == ['rotators']


def test_the_display_entry_goes_back_to_the_last_display_tab(
    http: TestClient, tournament: StoredTournament
) -> None:
    def display_link() -> str:
        parser = AdvancedHTMLParser()
        parser.parseStr(http.get(f'/event/{EVENT_ID}/players').text)
        link = parser.getElementsByAttr('data-testid', 'nav-admin-event-views-link')[0]
        return link.getAttribute('hx-get')

    for tab in ('timers', 'menus'):
        http.get(f'/event/{EVENT_ID}/{tab}')
        assert display_link() == f'/event/{EVENT_ID}/{tab}'


def test_a_paged_screen_preview_shows_that_it_has_pages(
    http: TestClient, api: ApiClient, tournament: StoredTournament
) -> None:
    family_with_pages(api, tournament, ScreenType.BOARDS)
    check_in_screen(api, tournament, 'Check-in')
    shown = http.get(
        f'/event/{EVENT_ID}/screens', params={'collection_view': 'preview'}
    ).text
    assert shown.count('feed-preview-paged') == 1
    assert '2 pages' in shown
