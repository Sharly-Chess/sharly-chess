"""What a visitor on the network reaches through displays and menus.

Kept apart from the administrator's tests: closing a visitor's client shuts the
application down for any client of the same module.
"""

from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTournament
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from tests.unit.http.test_display_controllers import (
    EVENT_ID,
    menu_of,
    send_menu,
    tournament,  # noqa: F401
)


def test_a_visitor_lists_menus_and_only_reaches_their_public_screens(
    lan: TestClient,
    api: ApiClient,
    tournament: StoredTournament,  # noqa: F811
) -> None:
    private = TestUtils.create_screen(
        api, EVENT_ID, 'Private', ScreenType.RESULTS, {'public': False}
    )
    public = TestUtils.create_screen(api, EVENT_ID, 'Public', ScreenType.RESULTS)
    other = TestUtils.create_screen(api, EVENT_ID, 'Other', ScreenType.RESULTS)
    menu_id = menu_of([private, public, other], 'Mixed')
    hidden_menu = menu_of([private], 'Staff only')
    with EventDatabase(EVENT_ID, True) as database:
        database.execute('UPDATE `info` SET `public` = 1')
    EventLoader.unload_event(EVENT_ID)

    listed = lan.get(f'/event/{EVENT_ID}/menus')
    assert listed.status_code == 200
    assert f'/view/menu/{EVENT_ID}/{menu_id}' in listed.text
    assert 'Mixed' in listed.text
    assert 'Staff only' not in listed.text
    assert '>Private<' not in listed.text

    page = lan.get(f'/view/menu/{EVENT_ID}/{menu_id}')
    assert 'data-page-title="Public"' in page.text
    assert '>Private<' not in page.text
    assert 'data-page-title="Private"' not in (
        lan.get(f'/view/menu/{EVENT_ID}/{hidden_menu}').text
    )


def test_a_visitor_only_reaches_the_public_screens_of_a_menu(
    lan: TestClient,
    api: ApiClient,
    tournament: StoredTournament,  # noqa: F811
) -> None:
    private = TestUtils.create_screen(
        api, EVENT_ID, 'Private', ScreenType.RESULTS, {'public': False}
    )
    public = TestUtils.create_screen(api, EVENT_ID, 'Public', ScreenType.RESULTS)
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'iPad')
    send_menu(api, controller.id, menu_of([private, public]))
    with EventDatabase(EVENT_ID, True) as database:
        database.execute('UPDATE `info` SET `public` = 1')
    EventLoader.unload_event(EVENT_ID)

    page = lan.get(f'/view/display-controller/{EVENT_ID}/{controller.id}')

    assert page.status_code == 200
    assert 'data-page-title="Public"' in page.text
    assert 'Private' not in page.text
    assert 'id="screen-menu"' not in page.text


def test_a_visitor_lands_on_the_display_page(lan: TestClient, api: ApiClient) -> None:
    visitor_event = 'test-display-controllers-visitor'
    TestUtils.create_event(visitor_event, overrides={'public': True})
    try:
        TestUtils.create_display_controller(api, visitor_event, 'iPad')
        response = lan.get(f'/event/{visitor_event}', follow_redirects=False)
        assert response.status_code in (301, 302, 303, 307)
        assert response.headers['location'] == f'/event/{visitor_event}/display'
    finally:
        EventLoader.unload_event(visitor_event)
        TestUtils.delete_event(visitor_event)
