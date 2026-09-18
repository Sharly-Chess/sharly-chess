"""What the shared collection renders for an administrator.

Every tab that lists things — screens, prize categories, display
controllers — is the same component with a different set of columns.
These read the markup it produces rather than looking at it.
"""

from collections.abc import Iterator

import pytest
from AdvancedHTMLParser import AdvancedHTMLParser
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_store import StoredTournament
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient

EVENT_ID = 'test-collections-http'
TOURNAMENT_NAME = 'test-collections-http-tournament'
RESULTS_SCREEN_NAME = 'A results screen'
IMAGE_SCREEN_NAME = 'An image screen'
CONTROLLER_NAME = 'A display controller'
FAMILY_UNIQ_ID = 'collections-http-family'
TINY_IMAGE_DATA_URI = 'data:image/gif;base64,R0lGODlhAQABAAAAACw='


@pytest.fixture
def tournament() -> Iterator[StoredTournament]:
    TestUtils.create_event(EVENT_ID)
    yield TestUtils.create_tournament(
        EVENT_ID, TOURNAMENT_NAME, json_file='test-screens'
    )
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def parse(response) -> AdvancedHTMLParser:
    assert response.status_code == 200
    parser = AdvancedHTMLParser()
    parser.parseStr(response.text)
    return parser


def section(parser: AdvancedHTMLParser, screen_type: ScreenType) -> str:
    """One accordion section of the screens tab. It is in the page whether
    or not it is open, which is a matter for the browser."""
    found = [
        element.getHTML()
        for element in parser.getElementsByTagName('div')
        if element.getAttribute('id') == f'admin-screens-show-{screen_type.value}'
    ]
    assert found, screen_type
    return found[0]


def item(markup: str, text: str) -> str:
    parser = AdvancedHTMLParser()
    parser.parseStr(markup)
    found = [
        element.getHTML()
        for element in parser.getElementsByTagName('article')
        + parser.getElementsByTagName('div')
        if element.getAttribute('data-testid')
        and element.getAttribute('data-testid').endswith('-item')
        and text in element.textContent
    ]
    assert found, text
    return found[0]


def header(markup: str) -> str:
    parser = AdvancedHTMLParser()
    parser.parseStr(markup)
    return ' '.join(
        element.textContent
        for element in parser.getElementsByTagName('div')
        if 'collection-list-header' in (element.getAttribute('class') or '').split()
    )


@pytest.mark.unit
def test_a_standalone_screen_is_listed_without_the_multi_screen_columns(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    """A results or image screen has no sets and no source tournament, so
    the columns for those are not in its section at all."""
    TestUtils.create_screen(api, EVENT_ID, RESULTS_SCREEN_NAME, ScreenType.RESULTS)
    TestUtils.create_screen(
        api,
        EVENT_ID,
        IMAGE_SCREEN_NAME,
        ScreenType.IMAGE,
        {
            'background_color_checkbox': True,
            'background_image_upload': TINY_IMAGE_DATA_URI,
        },
    )
    listed = parse(
        http.get(
            f'/event/{EVENT_ID}/screens',
            params={'collection_view': 'list', 'show_family_screens': 'true'},
        )
    )
    for screen_type, name in (
        (ScreenType.RESULTS, RESULTS_SCREEN_NAME),
        (ScreenType.IMAGE, IMAGE_SCREEN_NAME),
    ):
        markup = section(listed, screen_type)
        assert 'Multi-Screen' not in header(markup)
        assert 'Content' not in header(markup)
        assert 'Timer' in header(markup)
        row = item(markup, name)
        assert 'collection-list-cell-source' not in row
        assert 'collection-list-cell-screen_sets' not in row
        assert 'No timer' in row


@pytest.mark.unit
def test_the_input_section_names_the_parts_of_a_multi_screen(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    """An input screen has a source and sets, and the parts of a
    multi-screen are listed beside the screens of their own."""
    TestUtils.create_screen(
        api,
        EVENT_ID,
        'An input screen',
        ScreenType.INPUT,
        {'init_set_tournament_id': tournament.id},
    )
    family = TestUtils.create_family(
        api, EVENT_ID, tournament, FAMILY_UNIQ_ID, ScreenType.INPUT, {'parts': 2}
    )
    TestUtils.update_family_name(EVENT_ID, family, '%t (%f to %l)')

    markup = section(
        parse(
            http.get(
                f'/event/{EVENT_ID}/screens',
                params={'collection_view': 'list', 'show_family_screens': 'true'},
            )
        ),
        ScreenType.INPUT,
    )
    assert 'Multi-Screen' not in header(markup)
    assert 'Content' in header(markup)
    assert 'Timer' in header(markup)
    assert TOURNAMENT_NAME in item(markup, TOURNAMENT_NAME)


@pytest.mark.unit
@pytest.mark.parametrize(
    ('view', 'footer'),
    [('list', 'collection-list-cell-actions'), ('cards', 'collection-card-footer')],
)
def test_a_display_controller_says_what_it_carries(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    view: str,
    footer: str,
):
    """The assignment is written as an arrow to the screen rather than a
    sentence, and an administrator keeps the controls a visitor does
    not."""
    screen = TestUtils.create_screen(
        api, EVENT_ID, RESULTS_SCREEN_NAME, ScreenType.RESULTS
    )
    TestUtils.create_display_controller(
        api, EVENT_ID, CONTROLLER_NAME, screen_uniq_id=screen.uniq_id
    )
    response = http.get(
        f'/event/{EVENT_ID}/display_controllers', params={'collection_view': view}
    )
    markup = item(response.text, CONTROLLER_NAME)
    assert RESULTS_SCREEN_NAME in markup
    assert 'Currently displaying' not in markup
    assert 'bi-arrow-right' in markup
    assert footer in markup


@pytest.mark.unit
@pytest.mark.parametrize(
    ('view', 'icon'), [('list', 'bi-grip-vertical'), ('cards', 'bi-arrows-move')]
)
def test_a_prize_category_is_dragged_by_the_icon_its_view_uses(
    http: TestClient, tournament: StoredTournament, view: str, icon: str
):
    """A row is taken by a grip and a card by a move handle, and prize
    categories are listed by the same component as everything else."""
    assert (
        http.post(f'/prizes/prize-group/create/{EVENT_ID}/{tournament.id}').status_code
        == 200
    )
    EventLoader.unload_event(EVENT_ID)
    group = next(
        iter(
            EventLoader()
            .load_event(EVENT_ID)
            .tournaments_by_name[TOURNAMENT_NAME]
            .prize_groups
        )
    )
    for name in ('First category', 'Second category'):
        created = http.post(
            f'/prizes/prize-category/create/{EVENT_ID}/{tournament.id}/{group.id}',
            data={'name': name},
        )
        assert created.status_code == 200

    response = http.get(f'/event/{EVENT_ID}/prizes', params={'collection_view': view})
    markup = item(response.text, 'First category')
    assert icon in markup


@pytest.mark.unit
@pytest.mark.parametrize('action', ['update', 'clone'])
def test_the_event_modal_opens_for_every_action(
    http: TestClient, tournament: StoredTournament, action: str
):
    """The event's own form, reached from the tab beside the tournaments
    rather than from the list."""
    response = http.get(f'/event-modal/{action}/{EVENT_ID}')
    assert response.status_code == 200


@pytest.mark.unit
def test_the_event_delete_modal_asks_before_archiving(
    http: TestClient, tournament: StoredTournament
):
    response = http.get(f'/current_events/event-modal/delete/{EVENT_ID}')
    assert response.status_code == 200
    assert 'archive' in response.text


@pytest.mark.unit
def test_the_display_controller_modals_open(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    assert http.get(f'/display-controller-modal/create/{EVENT_ID}').status_code == 200
    controller = TestUtils.create_display_controller(api, EVENT_ID, CONTROLLER_NAME)
    for action in ('update', 'delete'):
        response = http.get(
            f'/display-controller-modal/{action}/{EVENT_ID}/{controller.id}'
        )
        assert response.status_code == 200


@pytest.mark.unit
def test_the_screens_of_a_rotator_are_listed_in_their_modal(
    http: TestClient, tournament: StoredTournament
):
    created = http.post(
        f'/rotator-create/{EVENT_ID}', data={'name': 'A rotator', 'delay': '15'}
    )
    assert created.status_code == 200
    EventLoader.unload_event(EVENT_ID)
    rotator_id = next(iter(EventLoader().load_event(EVENT_ID).rotators_by_id))
    response = http.get(f'/rotator-screens-modal/{EVENT_ID}/{rotator_id}')
    assert response.status_code == 200
    assert 'screens-add-button' in response.text


@pytest.mark.unit
def test_the_prize_category_modal_opens(http: TestClient, tournament: StoredTournament):
    assert (
        http.post(f'/prizes/prize-group/create/{EVENT_ID}/{tournament.id}').status_code
        == 200
    )
    EventLoader.unload_event(EVENT_ID)
    group = next(
        iter(
            EventLoader()
            .load_event(EVENT_ID)
            .tournaments_by_name[TOURNAMENT_NAME]
            .prize_groups
        )
    )
    response = http.get(
        f'/prizes/prize-category-modal/create/{EVENT_ID}/{tournament.id}/{group.id}'
    )
    assert response.status_code == 200
