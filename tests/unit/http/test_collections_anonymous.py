"""The display page a visitor of a public event is offered.

A visitor first chooses a feed to follow, or chooses to see everything, then
opens a screen, menu or rotator from static previews. Nothing on the page
changes anything.
"""

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from AdvancedHTMLParser import AdvancedHTMLParser
from litestar.testing import TestClient

from database.sqlite.event.event_store import StoredDisplayController, StoredScreen
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient

EVENT_ID = 'test-anonymous-collections'
TOURNAMENT_NAME = 'test-anonymous-collections-tournament'
ROTATOR_SCREEN_NAME = 'Rotator screen'
ROTATOR_NAME = 'A rotator'
IMAGE_SCREEN_NAME = 'An image screen'
INPUT_SCREEN_NAME = 'An input screen'
FAMILY_UNIQ_ID = 'anonymous-input-family'
ASSIGNED_CONTROLLER_NAME = 'Assigned controller'
UNASSIGNED_CONTROLLER_NAME = 'Unassigned controller'
TINY_IMAGE_DATA_URI = 'data:image/gif;base64,R0lGODlhAQABAAAAACw='


@dataclass
class Fixtures:
    input_screen: StoredScreen
    image_screen: StoredScreen
    rotator_id: int
    assigned_controller: StoredDisplayController
    unassigned_controller: StoredDisplayController


@pytest.fixture(scope='module')
def tabs(api: ApiClient) -> Iterator[Fixtures]:
    TestUtils.create_event(EVENT_ID, overrides={'public': True})
    tournament = TestUtils.create_tournament(
        EVENT_ID, TOURNAMENT_NAME, json_file='test-screens'
    )
    input_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        INPUT_SCREEN_NAME,
        ScreenType.BOARDS,
        {
            'accepts_input': True,
            'init_set_tournament_ids': [tournament.id],
            'public': True,
        },
    )
    family = TestUtils.create_family(
        api,
        EVENT_ID,
        tournament,
        FAMILY_UNIQ_ID,
        ScreenType.BOARDS,
        {'accepts_input': True, 'parts': 2, 'public': True},
    )
    TestUtils.update_family_name(EVENT_ID, family, '%t (%f to %l)')
    rotator_screen = TestUtils.create_screen(
        api, EVENT_ID, ROTATOR_SCREEN_NAME, ScreenType.RESULTS, {'public': True}
    )
    yield Fixtures(
        input_screen=input_screen,
        image_screen=TestUtils.create_screen(
            api,
            EVENT_ID,
            IMAGE_SCREEN_NAME,
            ScreenType.IMAGE,
            {
                'public': True,
                'background_color_checkbox': True,
                'background_image_upload': TINY_IMAGE_DATA_URI,
            },
        ),
        rotator_id=TestUtils.create_rotator(
            api, EVENT_ID, ROTATOR_NAME, screen_ids=[rotator_screen.id]
        ),
        assigned_controller=TestUtils.create_display_controller(
            api,
            EVENT_ID,
            ASSIGNED_CONTROLLER_NAME,
            screen_uniq_id=input_screen.uniq_id,
        ),
        unassigned_controller=TestUtils.create_display_controller(
            api, EVENT_ID, UNASSIGNED_CONTROLLER_NAME
        ),
    )
    TestUtils.delete_event(EVENT_ID)


def display(lan: TestClient, query: str = '') -> str:
    response = lan.get(f'/event/{EVENT_ID}/display{query}')
    assert response.status_code == 200
    return response.text


def tiles(text: str, test_id: str) -> list[str]:
    parser = AdvancedHTMLParser()
    parser.parseStr(text)
    return [
        element.getHTML()
        for element in parser.getElementsByAttr('data-testid', test_id)
    ]


@pytest.mark.unit
def test_a_visitor_starts_by_choosing_a_feed(lan: TestClient, tabs: Fixtures):
    landing = lan.get(f'/event/{EVENT_ID}', follow_redirects=False)
    assert landing.headers['location'] == f'/event/{EVENT_ID}/display'

    text = display(lan)
    feeds = tiles(text, 'display-feed')
    assert len(feeds) == 2
    for controller in (tabs.assigned_controller, tabs.unassigned_controller):
        assert f'href="/view/display-controller/{EVENT_ID}/{controller.id}"' in text
    assert 'data-testid="display-show-all"' in text
    assert 'no-sidebar' in text


@pytest.mark.unit
def test_showing_all_offers_static_previews_of_the_screens(
    lan: TestClient, tabs: Fixtures
):
    text = display(lan, '?browse=true')
    screens = tiles(text, 'display-screen')
    assert any(INPUT_SCREEN_NAME in tile for tile in screens)
    assert any(IMAGE_SCREEN_NAME in tile for tile in screens)
    assert (
        f'src="/view/screen/{EVENT_ID}/{tabs.input_screen.uniq_id}?preview=true"'
        in text
    )
    assert 'hx-patch' not in text
    assert 'modal' not in ''.join(screens)


@pytest.mark.unit
def test_a_paged_screen_is_one_tile_with_a_link_per_page(
    lan: TestClient, tabs: Fixtures
):
    text = display(lan, '?browse=true&kind=screens&type=boards')
    paged = [
        tile for tile in tiles(text, 'display-screen') if 'display-page-links' in tile
    ]
    assert len(paged) == 1
    for page in (1, 2):
        assert f'/view/screen/{EVENT_ID}/{FAMILY_UNIQ_ID}:{page:03}"' in paged[0]


@pytest.mark.unit
def test_a_type_chip_keeps_the_screens_of_one_type(lan: TestClient, tabs: Fixtures):
    text = display(lan, '?browse=true&kind=screens&type=image')
    screens = tiles(text, 'display-screen')
    assert len(screens) == 1
    assert IMAGE_SCREEN_NAME in screens[0]


@pytest.mark.unit
def test_rotators_are_offered_beside_the_screens(lan: TestClient, tabs: Fixtures):
    text = display(lan, '?browse=true')
    assert 'data-testid="display-kind-rotators"' in text
    rotators = tiles(display(lan, '?browse=true&kind=rotators'), 'display-rotator')
    assert len(rotators) == 1
    assert ROTATOR_NAME in rotators[0]
    assert f'/view/rotator/{EVENT_ID}/{tabs.rotator_id}' in rotators[0]


@pytest.mark.unit
def test_the_former_visitor_tabs_lead_to_the_display_page(
    lan: TestClient, tabs: Fixtures
):
    for path, location in (
        ('boards-screens', '?browse=true&kind=screens&type=boards'),
        ('rotators', '?browse=true&kind=rotators'),
        ('menus', '?browse=true&kind=menus'),
        ('display_controllers', ''),
    ):
        response = lan.get(f'/event/{EVENT_ID}/{path}', follow_redirects=False)
        assert response.headers['location'] == f'/event/{EVENT_ID}/display{location}'
