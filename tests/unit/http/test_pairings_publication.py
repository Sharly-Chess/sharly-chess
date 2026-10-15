"""Publishing the pairings of a round to the screens and the online
services, over HTTP."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from data.tournament import Tournament
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from tests.unit.http.events import EventUnderTest
from utils.enum import Result

EVENT_ID = 'test-pairings-publication'
TOURNAMENT_NAME = 'test-pairings-publication-tournament'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


@pytest.fixture
def tournament() -> Iterator[Tournament]:
    EVENT.create(json_file='tec-swiss-unpaired')
    yield EVENT.tournament()
    EVENT.delete()


@pytest.fixture
def round_robin() -> Iterator[Tournament]:
    EVENT.create(json_file='tec-round-robin')
    yield EVENT.tournament()
    EVENT.delete()


def public_tournament() -> Tournament:
    EventLoader.unload_event(EVENT_ID)
    event = EventLoader().load_event(EVENT_ID, public_view=True)
    EVENT._loaded.append(event)
    return event.tournaments_by_name[TOURNAMENT_NAME]


def pair_round(http: TestClient, tournament: Tournament, round_: int) -> None:
    response = http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/{round_}')
    assert response.status_code == 200
    assert EVENT.tournament().round_has_pairings(round_)


def publish(http: TestClient, tournament: Tournament, round_: int) -> None:
    response = http.put(f'/pairings/publish/{EVENT_ID}/{tournament.id}/{round_}')
    assert response.status_code == 200


def unpublish(http: TestClient, tournament: Tournament, round_: int) -> None:
    response = http.put(f'/pairings/unpublish/{EVENT_ID}/{tournament.id}/{round_}')
    assert response.status_code == 200


def enter_result(http: TestClient, tournament: Tournament, round_: int) -> None:
    board = EVENT.tournament().get_round_boards(round_)[0]
    response = http.put(
        f'/pairing/set-result/{EVENT_ID}/{tournament.id}/{round_}/{board.id}'
        f'/{Result.WIN.value}'
    )
    assert response.status_code == 200


def enter_all_results(http: TestClient, tournament: Tournament, round_: int) -> None:
    for board in EVENT.tournament().get_round_boards(round_):
        if board.black_player_id:
            http.put(
                f'/pairing/set-result/{EVENT_ID}/{tournament.id}/{round_}/{board.id}'
                f'/{Result.DRAW.value}'
            )
    assert EVENT.tournament().is_round_finished(round_)


@pytest.mark.unit
def test_a_paired_round_is_not_published(http: TestClient, tournament: Tournament):
    """The arbiter works on the round; the public does not see it yet."""
    pair_round(http, tournament, 1)
    assert EVENT.tournament().current_round == 1
    assert EVENT.tournament().published_round == 0
    public = public_tournament()
    assert public.current_round == 0
    assert not public.boards


@pytest.mark.unit
def test_a_published_round_is_public(http: TestClient, tournament: Tournament):
    pair_round(http, tournament, 1)
    publish(http, tournament, 1)
    assert EVENT.tournament().published_round == 1
    public = public_tournament()
    assert public.current_round == 1
    assert public.boards == EVENT.tournament().get_round_boards(1)


@pytest.mark.unit
def test_the_next_round_stays_hidden_until_published(
    http: TestClient, tournament: Tournament
):
    """The public keeps seeing the round played, results included, while
    the next one is checked."""
    pair_round(http, tournament, 1)
    publish(http, tournament, 1)
    enter_all_results(http, tournament, 1)
    pair_round(http, tournament, 2)
    assert EVENT.tournament().current_round == 2
    public = public_tournament()
    assert public.current_round == 1
    assert public.max_ranking_round == 1
    publish(http, tournament, 2)
    assert public_tournament().current_round == 2


@pytest.mark.unit
def test_an_unpaired_round_cannot_be_published(
    http: TestClient, tournament: Tournament
):
    publish(http, tournament, 1)
    assert EVENT.tournament().published_round == 0


@pytest.mark.unit
def test_publishing_a_round_publishes_the_rounds_before_it(
    http: TestClient, round_robin: Tournament
):
    http.post(f'/pairings/unpair-tournament/{EVENT_ID}/{round_robin.id}')
    http.post(f'/pairings/generate/{EVENT_ID}/{round_robin.id}')
    assert EVENT.tournament().is_fully_paired
    enter_all_results(http, round_robin, 1)
    enter_all_results(http, round_robin, 2)
    publish(http, round_robin, 3)
    assert EVENT.tournament().published_round == 3
    assert public_tournament().current_round == 3
    publish(http, round_robin, 2)
    assert EVENT.tournament().published_round == 3


@pytest.mark.unit
def test_a_round_is_published_once_the_rounds_before_it_are_finished(
    http: TestClient, round_robin: Tournament
):
    http.post(f'/pairings/unpair-tournament/{EVENT_ID}/{round_robin.id}')
    http.post(f'/pairings/generate/{EVENT_ID}/{round_robin.id}')
    publish(http, round_robin, 1)
    publish(http, round_robin, 2)
    assert EVENT.tournament().published_round == 1
    enter_all_results(http, round_robin, 1)
    publish(http, round_robin, 2)
    assert EVENT.tournament().published_round == 2


@pytest.mark.unit
def test_a_round_without_results_can_be_unpublished(
    http: TestClient, tournament: Tournament
):
    pair_round(http, tournament, 1)
    publish(http, tournament, 1)
    unpublish(http, tournament, 1)
    assert EVENT.tournament().published_round == 0
    assert public_tournament().current_round == 0


@pytest.mark.unit
def test_a_round_with_results_cannot_be_unpublished(
    http: TestClient, tournament: Tournament
):
    pair_round(http, tournament, 1)
    publish(http, tournament, 1)
    enter_result(http, tournament, 1)
    unpublish(http, tournament, 1)
    assert EVENT.tournament().published_round == 1


@pytest.mark.unit
def test_unpairing_a_published_round_unpublishes_it(
    http: TestClient, tournament: Tournament
):
    """Pairing the round again does not show it before it is checked."""
    pair_round(http, tournament, 1)
    publish(http, tournament, 1)
    http.post(f'/pairings/unpair/{EVENT_ID}/{tournament.id}/1')
    assert EVENT.tournament().stored_tournament.published_round == 0
    pair_round(http, tournament, 1)
    assert EVENT.tournament().published_round == 0


@pytest.mark.unit
def test_the_round_robin_round_in_play_is_the_published_one(
    http: TestClient, round_robin: Tournament
):
    """Every round is paired at once: publishing the next one, once the
    previous one is finished, moves the tournament on."""
    http.post(f'/pairings/unpair-tournament/{EVENT_ID}/{round_robin.id}')
    http.post(f'/pairings/generate/{EVENT_ID}/{round_robin.id}')
    assert EVENT.tournament().current_round == 1
    assert public_tournament().current_round == 0
    page = http.get(f'/event/{EVENT_ID}/pairings/{round_robin.id}/1')
    assert f'/pairings/publish/{EVENT_ID}/{round_robin.id}/1' in page.text
    publish(http, round_robin, 1)
    enter_all_results(http, round_robin, 1)
    publish(http, round_robin, 2)
    assert EVENT.tournament().current_round == 2
    assert public_tournament().current_round == 2


@pytest.mark.unit
def test_the_publish_button_is_offered_once_paired(
    http: TestClient, tournament: Tournament
):
    pair_round(http, tournament, 1)
    page = http.get(f'/event/{EVENT_ID}/pairings/{tournament.id}/1')
    assert page.status_code == 200
    assert f'/pairings/publish/{EVENT_ID}/{tournament.id}/1' in page.text
    publish(http, tournament, 1)
    page = http.get(f'/event/{EVENT_ID}/pairings/{tournament.id}/1')
    assert f'/pairings/unpublish/{EVENT_ID}/{tournament.id}/1' in page.text


def pairings_page(http: TestClient, tournament: Tournament) -> str:
    return http.get(f'/event/{EVENT_ID}/pairings/{tournament.id}/1').text


@pytest.mark.unit
def test_unpublished_pairings_shown_on_screens_are_flagged(
    http: TestClient, api: ApiClient, tournament: Tournament
):
    TestUtils.create_screen(
        api,
        EVENT_ID,
        'boards',
        ScreenType.BOARDS,
        {'init_set_tournament_id': tournament.id},
    )
    pair_round(http, tournament, 1)
    assert EVENT.tournament().shown_on_screens
    assert 'are not shown on the screens' in pairings_page(http, tournament)
    publish(http, tournament, 1)
    assert 'are not shown on the screens' not in pairings_page(http, tournament)


@pytest.mark.unit
def test_unpublished_pairings_seen_by_nobody_are_not_flagged(
    http: TestClient, tournament: Tournament
):
    pair_round(http, tournament, 1)
    assert not EVENT.tournament().shown_on_screens
    assert not EVENT.tournament().uploaded_online
    assert 'are not published' not in pairings_page(http, tournament)


@pytest.mark.unit
def test_unpublished_pairings_of_an_uploaded_tournament_are_flagged(
    http: TestClient, tournament: Tournament
):
    event = EVENT.load()
    stored_event = event.stored_event
    stored_event.enabled_plugins = [*stored_event.enabled_plugins, 'chess_results']
    stored_tournament = event.tournaments_by_name[TOURNAMENT_NAME].stored_tournament
    stored_tournament.plugin_data['chess_results'] = {'tnr': '123456'}
    with EventDatabase(EVENT_ID, True) as database:
        database.update_stored_event(stored_event)
        database.update_stored_tournament(stored_tournament)
    pair_round(http, tournament, 1)
    assert EVENT.tournament().uploaded_online
    assert 'are not sent to the online services' in pairings_page(http, tournament)


@pytest.mark.unit
def test_pairings_waiting_for_an_unfinished_round_say_so(
    http: TestClient, api: ApiClient, round_robin: Tournament
):
    TestUtils.create_screen(
        api,
        EVENT_ID,
        'boards',
        ScreenType.BOARDS,
        {'init_set_tournament_id': round_robin.id},
    )
    http.post(f'/pairings/unpair-tournament/{EVENT_ID}/{round_robin.id}')
    http.post(f'/pairings/generate/{EVENT_ID}/{round_robin.id}')
    publish(http, round_robin, 1)
    page = http.get(f'/event/{EVENT_ID}/pairings/{round_robin.id}/2').text
    assert 'Round 1 is not finished' in page
    assert 'are not shown on the screens' not in page
    enter_all_results(http, round_robin, 1)
    page = http.get(f'/event/{EVENT_ID}/pairings/{round_robin.id}/2').text
    assert 'are not shown on the screens' in page
    assert 'Round 1 is not finished' not in page


@pytest.mark.unit
def test_unpublished_pairings_of_a_tournament_with_ffe_credentials_are_flagged(
    http: TestClient, tournament: Tournament
):
    event = EVENT.load()
    stored_event = event.stored_event
    stored_event.federation = 'FRA'
    stored_event.enabled_plugins = [*stored_event.enabled_plugins, 'ffe']
    stored_tournament = event.tournaments_by_name[TOURNAMENT_NAME].stored_tournament
    stored_tournament.plugin_data['ffe'] = {'ffe_id': 12345, 'password': 'secret'}
    with EventDatabase(EVENT_ID, True) as database:
        database.update_stored_event(stored_event)
        database.update_stored_tournament(stored_tournament)
    pair_round(http, tournament, 1)
    assert EVENT.tournament().uploaded_online
    assert 'are not sent to the online services' in pairings_page(http, tournament)
