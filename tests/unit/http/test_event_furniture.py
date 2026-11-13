"""Menus, rotators and accounts, over HTTP.

The three sit beside the tournaments in an event: what the public screens
link to, what cycles between them, and who is allowed to touch what.
"""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-furniture-http'
EVENT = EventUnderTest(EVENT_ID)


@pytest.fixture
def event() -> Iterator[str]:
    EVENT.create()
    yield EVENT_ID
    EVENT.delete()


@pytest.mark.unit
def test_a_menu_is_created_and_deleted(http: TestClient, event: str):
    response = http.post(f'/menu-create/{EVENT_ID}', data={'name': 'Main menu'})
    assert response.status_code == 200
    assert list(EVENT.load().menus_by_name) == ['Main menu']
    menu_id = next(iter(EVENT.load().menus_by_id))
    assert http.delete(f'/menu-delete/{EVENT_ID}/{menu_id}').status_code == 200
    assert list(EVENT.load().menus_by_name) == []


@pytest.mark.unit
def test_two_menus_cannot_share_a_name(http: TestClient, event: str):
    http.post(f'/menu-create/{EVENT_ID}', data={'name': 'Main menu'})
    response = http.post(f'/menu-create/{EVENT_ID}', data={'name': 'Main menu'})
    assert response.status_code == 200
    assert 'This name is already used.' in response.text
    assert list(EVENT.load().menus_by_name) == ['Main menu']


@pytest.mark.unit
def test_a_menu_may_go_unnamed(http: TestClient, event: str):
    """An unnamed menu is named after what it holds, so the field is not
    required the way a rotator's is."""
    response = http.post(f'/menu-create/{EVENT_ID}', data={'name': ''})
    assert response.status_code == 200
    assert len(EVENT.load().menus_by_id) == 1


@pytest.mark.unit
def test_a_rotator_is_created_and_deleted(http: TestClient, event: str):
    response = http.post(
        f'/rotator-create/{EVENT_ID}', data={'name': 'Hall screens', 'delay': '15'}
    )
    assert response.status_code == 200
    assert list(EVENT.load().rotators_by_name) == ['Hall screens']
    rotator_id = next(iter(EVENT.load().rotators_by_id))
    assert http.delete(f'/rotator-delete/{EVENT_ID}/{rotator_id}').status_code == 200
    assert list(EVENT.load().rotators_by_name) == []


@pytest.mark.unit
def test_a_rotator_needs_a_name(http: TestClient, event: str):
    response = http.post(
        f'/rotator-create/{EVENT_ID}', data={'name': '', 'delay': '15'}
    )
    assert response.status_code == 200
    assert 'This field is required.' in response.text
    assert list(EVENT.load().rotators_by_name) == []


@pytest.mark.unit
def test_a_rotator_waits_at_least_a_second_on_each_screen(http: TestClient, event: str):
    """A delay of zero would leave the screens unreadable."""
    response = http.post(
        f'/rotator-create/{EVENT_ID}', data={'name': 'Hall screens', 'delay': '0'}
    )
    assert response.status_code == 200
    assert list(EVENT.load().rotators_by_name) == []


@pytest.mark.unit
def test_an_account_needs_a_name(http: TestClient, event: str):
    before = len(EVENT.load().stored_event.stored_accounts)
    response = http.post(
        f'/account-create/{EVENT_ID}',
        data={'last_name': '', 'first_name': 'Arbiter'},
    )
    assert response.status_code == 200
    assert 'This field is required.' in response.text
    assert len(EVENT.load().stored_event.stored_accounts) == before


@pytest.mark.unit
def test_an_account_needs_an_address_that_could_receive_mail(
    http: TestClient, event: str
):
    before = len(EVENT.load().stored_event.stored_accounts)
    response = http.post(
        f'/account-create/{EVENT_ID}',
        data={'last_name': 'Arbiter', 'mail': 'not-an-address'},
    )
    assert response.status_code == 200
    assert 'Please supply a valid email address.' in response.text
    assert len(EVENT.load().stored_event.stored_accounts) == before


@pytest.fixture
def rotator(http: TestClient, event: str) -> int:
    assert (
        http.post(
            f'/rotator-create/{EVENT_ID}',
            data={'name': 'Hall screens', 'delay': '15'},
        ).status_code
        == 200
    )
    return next(iter(EVENT.load().rotators_by_id))


@pytest.mark.unit
def test_a_screen_joins_a_rotator_and_leaves_it(
    http: TestClient, api: ApiClient, event: str, rotator: int
):
    """A rotator shows the screens given to it in turn, so what it holds
    is the whole of its configuration."""
    screen = TestUtils.create_screen(
        api, EVENT_ID, 'Rotated screen', ScreenType.RESULTS, {'public': True}
    )
    added = http.post(
        f'/rotating-screens/create/{EVENT_ID}/{rotator}',
        data={'item_id': f'screen:{screen.id}'},
    )
    assert added.status_code == 200
    assert [
        screen.name for screen in EVENT.load().rotators_by_id[rotator].rotating_screens
    ] == ['Rotated screen']

    rotating_id = next(
        iter(EVENT.load().rotators_by_id[rotator].rotating_screens_by_id)
    )
    removed = http.delete(f'/rotator-screen-delete/{EVENT_ID}/{rotator}/{rotating_id}')
    assert removed.status_code == 200
    assert not EVENT.load().rotators_by_id[rotator].rotating_screens


@pytest.mark.unit
def test_a_duplicated_rotator_carries_its_screens(
    http: TestClient, api: ApiClient, event: str, rotator: int
):
    screen = TestUtils.create_screen(
        api, EVENT_ID, 'Rotated screen', ScreenType.RESULTS, {'public': True}
    )
    http.post(
        f'/rotating-screens/create/{EVENT_ID}/{rotator}',
        data={'item_id': f'screen:{screen.id}'},
    )
    response = http.post(
        f'/rotator-clone/{EVENT_ID}/{rotator}',
        data={'name': 'Duplicated rotator', 'delay': '15'},
    )
    assert response.status_code == 200
    copies = [
        one
        for one in EVENT.load().rotators_by_id.values()
        if one.name == 'Duplicated rotator'
    ]
    assert len(copies) == 1
    assert len(copies[0].rotating_screens) == 1


@pytest.fixture
def screen_and_paged_screen(api: ApiClient, event: str) -> tuple[int, int]:
    tournament = TestUtils.create_tournament(EVENT_ID, 'Open', json_file='test-screens')
    screen = TestUtils.create_screen(
        api, EVENT_ID, 'Results', ScreenType.RESULTS, {'public': True}
    )
    family = TestUtils.create_family(
        api, EVENT_ID, tournament, 'ranking-pages', ScreenType.RANKING
    )
    assert screen.id is not None and family.id is not None
    return screen.id, family.id


@pytest.mark.unit
def test_a_rotator_offers_screens_and_paged_screens_in_one_list(
    http: TestClient,
    event: str,
    rotator: int,
    screen_and_paged_screen: tuple[int, int],
):
    screen_id, family_id = screen_and_paged_screen
    modal = http.get(f'/rotator-screens-modal/{EVENT_ID}/{rotator}')
    assert f'value="screen:{screen_id}"' in modal.text
    assert f'value="family:{family_id}"' in modal.text

    for item_id in (f'screen:{screen_id}', f'family:{family_id}'):
        response = http.post(
            f'/rotating-screens/create/{EVENT_ID}/{rotator}',
            data={'item_id': item_id},
        )
        assert response.status_code == 200
    loaded = EVENT.load().rotators_by_id[rotator]
    assert [screen.id for screen in loaded.screens] == [screen_id]
    assert [family.id for family in loaded.families] == [family_id]


@pytest.mark.unit
def test_a_rotator_refuses_what_is_not_a_screen(
    http: TestClient,
    event: str,
    rotator: int,
    screen_and_paged_screen: tuple[int, int],
):
    screen_id, _family_id = screen_and_paged_screen
    for item_id in (str(screen_id), f'rotator:{rotator}', 'screen:999'):
        http.post(
            f'/rotating-screens/create/{EVENT_ID}/{rotator}',
            data={'item_id': item_id},
        )
    assert not EVENT.load().rotators_by_id[rotator].rotating_screens


@pytest.mark.unit
def test_a_menu_offers_screens_and_paged_screens_in_one_list(
    http: TestClient, event: str, screen_and_paged_screen: tuple[int, int]
):
    screen_id, family_id = screen_and_paged_screen
    http.post(f'/menu-create/{EVENT_ID}', data={'name': 'Main menu'})
    menu_id = next(iter(EVENT.load().menus_by_id))
    modal = http.get(f'/menu-items-modal/{EVENT_ID}/{menu_id}')
    assert f'value="screen:{screen_id}"' in modal.text
    assert f'value="family:{family_id}"' in modal.text

    for item_id in (f'screen:{screen_id}', f'family:{family_id}', 'screen:999'):
        http.post(f'/menu-items/create/{EVENT_ID}/{menu_id}', data={'item_id': item_id})
    menu = EVENT.load().menus_by_id[menu_id]
    assert [screen.id for screen in menu.screens] == [screen_id]
    assert [family.id for family in menu.families] == [family_id]
