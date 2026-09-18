"""What a visitor is offered on the screens, rotators and controllers
tabs of a public event.

Those tabs are shown to anyone at the venue, with the controls that
change anything left out: no actions column, no inline editing, no link
to the editor. The rows stay clickable, because following one is how a
visitor opens the screen it names.
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
        ScreenType.INPUT,
        {'init_set_tournament_id': tournament.id, 'public': True},
    )
    family = TestUtils.create_family(
        api,
        EVENT_ID,
        tournament,
        FAMILY_UNIQ_ID,
        ScreenType.INPUT,
        {'parts': 2, 'public': True},
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


def page(lan: TestClient, path: str, view: str = 'list') -> AdvancedHTMLParser:
    response = lan.get(f'/event/{EVENT_ID}/{path}?collection_view={view}')
    assert response.status_code == 200
    parser = AdvancedHTMLParser()
    parser.parseStr(response.text)
    return parser


def header(parser: AdvancedHTMLParser) -> str:
    return ' '.join(
        element.textContent
        for element in parser.getElementsByTagName('div')
        if 'collection-list-header' in (element.getAttribute('class') or '').split()
    )


def items(parser: AdvancedHTMLParser, test_id: str) -> list[str]:
    return [
        element.getHTML()
        for element in parser.getElementsByTagName('article')
        + parser.getElementsByTagName('div')
        if element.getAttribute('data-testid') == test_id
    ]


def item(parser: AdvancedHTMLParser, test_id: str, text: str) -> str:
    """The markup of the one row or card holding this text."""
    found = [markup for markup in items(parser, test_id) if text in markup]
    assert found, f'no {test_id} holding {text}'
    return found[0]


@pytest.mark.unit
def test_a_screen_row_is_followed_but_not_edited(lan: TestClient, tabs: Fixtures):
    listed = page(lan, 'input-screens')
    assert 'Actions' not in header(listed)
    assert 'Content' in header(listed)
    assert 'Timer' in header(listed)

    markup = item(listed, 'screens-item', INPUT_SCREEN_NAME)
    assert 'collection-list-row-actionable' in markup
    assert 'collection-list-cell-actions' not in markup
    assert 'collection-inline-edit' not in markup
    assert 'bi-pencil-fill' not in markup
    assert 'collection-list-cell-source' not in markup
    assert '1 set' in markup
    assert 'No timer' in markup


@pytest.mark.unit
def test_a_multi_screen_row_says_which_one_it_is(lan: TestClient, tabs: Fixtures):
    """A part of a multi-screen is named after the range it carries, and
    is badged as one so it is not mistaken for a screen of its own."""
    parts = [
        markup
        for markup in items(page(lan, 'input-screens'), 'screens-item')
        if 'badge' in markup
    ]
    assert len(parts) == 2
    markup = parts[0]
    assert 'Multi-Screen' in markup
    assert TOURNAMENT_NAME in markup
    assert 'bi-window-split' not in markup
    assert 'collection-list-cell-source' not in markup
    assert 'No timer' in markup


@pytest.mark.unit
def test_a_screen_card_carries_no_editor_link(lan: TestClient, tabs: Fixtures):
    markup = item(
        page(lan, 'input-screens', 'cards'), 'screens-item', INPUT_SCREEN_NAME
    )
    assert 'collection-card-actionable' in markup
    assert 'collection-card-footer' not in markup
    assert 'screen-eye-' not in markup


@pytest.mark.unit
def test_a_standalone_screen_type_drops_the_columns_it_has_no_use_for(
    lan: TestClient, tabs: Fixtures
):
    """An image screen has neither sets nor a source tournament, so those
    columns are not shown at all."""
    listed = page(lan, 'image-screens')
    assert 'Multi-Screen' not in header(listed)
    assert 'Content' not in header(listed)

    markup = item(listed, 'screens-item', IMAGE_SCREEN_NAME)
    assert 'collection-list-cell-source' not in markup
    assert 'collection-list-cell-screen_sets' not in markup


@pytest.mark.unit
def test_a_rotator_row_is_followed_but_not_edited(lan: TestClient, tabs: Fixtures):
    listed = page(lan, 'rotators')
    assert 'Actions' not in header(listed)

    markup = item(listed, 'rotators-item', ROTATOR_NAME)
    assert 'collection-list-cell-actions' not in markup
    assert 'collection-inline-edit' not in markup
    assert 'collection-list-row-actionable' in markup
    assert f'/view/rotator/{EVENT_ID}/{tabs.rotator_id}' in markup

    card = item(page(lan, 'rotators', 'cards'), 'rotators-item', ROTATOR_NAME)
    assert 'collection-card-actionable' in card
    assert 'collection-card-footer' not in card
    assert 'bi-eye' not in card


@pytest.mark.unit
def test_a_display_controller_shows_what_it_is_pointed_at(
    lan: TestClient, tabs: Fixtures
):
    """A controller sends a screen to a display, so what a visitor is
    shown is which screen it carries — and nothing to change it with."""
    listed = page(lan, 'display_controllers')
    assert 'Actions' not in header(listed)

    assigned = item(listed, 'display-controllers-item', ASSIGNED_CONTROLLER_NAME)
    assert 'collection-list-cell-actions' not in assigned
    assert 'collection-list-row-actionable' in assigned
    assert (
        f'/view/display-controller/{EVENT_ID}/{tabs.assigned_controller.id}' in assigned
    )
    assert INPUT_SCREEN_NAME in assigned

    unassigned = item(listed, 'display-controllers-item', UNASSIGNED_CONTROLLER_NAME)
    assert 'None' in unassigned
    assert 'collection-list-row-actionable' not in unassigned
