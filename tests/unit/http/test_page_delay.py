"""How long the pages of a multi-screen are shown: its own pace when it sets
one, wherever its pages turn, otherwise the feed's default or the rotator's
delay."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from common.sharly_chess_config import SharlyChessConfig
from data.loader import EventLoader
from database.sqlite.event.event_store import StoredTournament
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient

EVENT_ID = 'test-page-delay-http'
FORM_HEADERS = {'Content-Type': 'application/x-www-form-urlencoded'}
ROTATOR_DELAY = 7


@pytest.fixture
def tournament() -> Iterator[StoredTournament]:
    TestUtils.create_event(EVENT_ID)
    yield TestUtils.create_tournament(
        EVENT_ID, 'Club tournament', json_file='test-screens'
    )
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def paged_screen(
    api: ApiClient, tournament: StoredTournament, page_delay: int | None
) -> tuple[int, str]:
    family = TestUtils.create_family(
        api,
        EVENT_ID,
        tournament,
        f'pages-{page_delay or 0}',
        ScreenType.BOARDS,
        {'parts': 2, 'page_delay': page_delay},
    )
    assert family.id is not None
    return family.id, family.uniq_id


@pytest.mark.unit
@pytest.mark.parametrize('page_delay', [20, None])
def test_a_feed_turns_the_pages_at_the_pace_of_the_paged_screen(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    page_delay: int | None,
):
    _family_id, uniq_id = paged_screen(api, tournament, page_delay)
    controller = TestUtils.create_display_controller(api, EVENT_ID, 'Projector')
    TestUtils.check_api_response(
        api.patch(
            f'/display-controller-assign/{EVENT_ID}/{controller.id}/family/{uniq_id}',
            headers=FORM_HEADERS,
        )
    )
    shown = http.get(f'/view/display-controller/{EVENT_ID}/{controller.id}').text
    expected = page_delay or SharlyChessConfig.default_rotator_delay
    assert f'every {expected}s' in shown


@pytest.mark.unit
@pytest.mark.parametrize('page_delay', [20, None])
def test_a_rotator_shows_a_paged_screen_at_its_own_pace(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    page_delay: int | None,
):
    family_id, _uniq_id = paged_screen(api, tournament, page_delay)
    single = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Single',
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id]},
    )
    rotator_id = TestUtils.create_rotator(
        api,
        EVENT_ID,
        'Lobby',
        overrides={'delay': ROTATOR_DELAY},
        screen_ids=[single.id],
        family_ids=[family_id],
    )
    single_page = http.get(f'/view/rotator/{EVENT_ID}/{rotator_id}/0').text
    assert f'every {ROTATOR_DELAY}s' in single_page
    paged_page = http.get(f'/view/rotator/{EVENT_ID}/{rotator_id}/1').text
    assert f'every {page_delay or ROTATOR_DELAY}s' in paged_page


@pytest.mark.unit
@pytest.mark.parametrize('page_delay', [20, None])
def test_a_paged_screen_opened_directly_goes_through_its_pages(
    http: TestClient,
    api: ApiClient,
    tournament: StoredTournament,
    page_delay: int | None,
):
    _family_id, uniq_id = paged_screen(api, tournament, page_delay)
    expected = page_delay or SharlyChessConfig.default_rotator_delay

    first = http.get(f'/view/paged-screen/{EVENT_ID}/{uniq_id}')
    assert first.status_code == 200
    assert f'/view/paged-screen/{EVENT_ID}/{uniq_id}/1"' in first.text
    assert f'every {expected}s' in first.text

    # Two pages: after the second comes the first again.
    second = http.get(f'/view/paged-screen/{EVENT_ID}/{uniq_id}/1')
    assert f'/view/paged-screen/{EVENT_ID}/{uniq_id}/2"' in second.text
    wrapped = http.get(f'/view/paged-screen/{EVENT_ID}/{uniq_id}/2')
    assert wrapped.status_code == 200
    assert f'/view/paged-screen/{EVENT_ID}/{uniq_id}/1"' in wrapped.text


@pytest.mark.unit
def test_a_paged_screen_taking_input_stays_on_its_page(
    http: TestClient, api: ApiClient, tournament: StoredTournament
):
    family = TestUtils.create_family(
        api,
        EVENT_ID,
        tournament,
        'check-in-pages',
        ScreenType.CHECK_IN,
        {'parts': 2},
    )
    shown = http.get(f'/view/paged-screen/{EVENT_ID}/{family.uniq_id}').text
    assert 'paged-screen-refresher' not in shown
