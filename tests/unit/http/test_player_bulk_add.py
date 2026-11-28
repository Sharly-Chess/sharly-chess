"""Adding several players found in the data sources at once."""

import json
from dataclasses import replace
from collections.abc import Iterator
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from litestar.testing import TestClient

from common.exception import SharlyChessException
from data.criteria.managers import SearchFilterManager
from data.input_output.managers import DataSourceManager
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer, StoredTeam
from tests.unit.http.events import EventUnderTest
from web.controllers.admin.player_admin_controller import PlayerAdminController
from utils.enum import EventType

EVENT_ID = 'test-player-bulk-add'
TOURNAMENT_NAME = 'Open'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)

SOURCE_ID = 'fake-source'

FOUND = {
    '1': StoredPlayer(
        id=None,
        last_name='ALPHA',
        first_name='Ann',
        date_of_birth=date(2001, 1, 1),
        federation='FRA',
        club='Club X',
    ),
    '2': StoredPlayer(
        id=None,
        last_name='BRAVO',
        first_name='Ben',
        date_of_birth=date(2002, 2, 2),
        federation='FRA',
        club='Club X',
    ),
    '3': StoredPlayer(
        id=None,
        last_name='CHARLIE',
        first_name='Cid',
        date_of_birth=date(2003, 3, 3),
        federation='FRA',
        club='Club X',
    ),
}


@pytest.fixture
def tournament_id() -> Iterator[int]:
    EVENT.create()
    yield EVENT.tournament().id
    EVENT.delete()


@pytest.fixture
def fetch_players() -> Iterator[AsyncMock]:
    """A data source finding the players of FOUND by their key."""

    async def found(player_source_ids: list[str], *_args: Any) -> Any:
        return {key: replace(FOUND[key]) for key in player_source_ids if key in FOUND}

    fetch = AsyncMock(side_effect=found)
    fake = SimpleNamespace(
        id=SOURCE_ID, name='Fake', is_available=True, fetch_players=fetch
    )
    with patch.object(DataSourceManager, 'active_objects', return_value=[fake]):
        yield fetch


@pytest.fixture
def data_source(fetch_players: AsyncMock) -> None:
    pass


def picks(*keys: str) -> list[str]:
    return [json.dumps([SOURCE_ID, key, FOUND[key].last_name]) for key in keys]


def last_names(players: Any) -> list[str]:
    return sorted(player.last_name for player in players)


@pytest.mark.unit
def test_the_modal_opens(http: TestClient, tournament_id: int):
    response = http.get(f'/player-bulk-add-modal/{EVENT_ID}')
    assert response.status_code == 200
    assert 'player-bulk-add-modal' in response.text


@pytest.mark.unit
def test_the_players_picked_enter_the_tournament(
    http: TestClient, tournament_id: int, data_source: None
):
    response = http.post(
        f'/player-bulk-add/{EVENT_ID}/{tournament_id}',
        data={'players': picks('1', '2', '3')},
    )
    assert response.status_code == 200
    assert '3 players added.' in response.text
    entered = EVENT.tournament().tournament_players
    assert last_names(entered) == ['ALPHA', 'BRAVO', 'CHARLIE']
    assert {player.club.name for player in entered} == {'Club X'}


@pytest.mark.unit
def test_a_player_already_entered_is_not_added_again(
    http: TestClient, tournament_id: int, data_source: None
):
    http.post(
        f'/player-bulk-add/{EVENT_ID}/{tournament_id}',
        data={'players': picks('1')},
    )
    response = http.post(
        f'/player-bulk-add/{EVENT_ID}/{tournament_id}',
        data={'players': picks('1', '2')},
    )
    assert response.status_code == 200
    assert '1 player added.' in response.text
    assert 'Not added: ALPHA' in response.text
    assert last_names(EVENT.tournament().tournament_players) == ['ALPHA', 'BRAVO']


@pytest.mark.unit
def test_the_same_person_picked_twice_is_added_once(
    http: TestClient, tournament_id: int, data_source: None
):
    """The same person can be found in two data sources."""
    twice = [*picks('1'), json.dumps([SOURCE_ID, '1', 'ALPHA again'])]
    response = http.post(
        f'/player-bulk-add/{EVENT_ID}/{tournament_id}', data={'players': twice}
    )
    assert response.status_code == 200
    assert 'Not added: ALPHA again' in response.text
    assert last_names(EVENT.tournament().tournament_players) == ['ALPHA']


@pytest.mark.unit
def test_players_are_not_added_without_a_tournament(
    http: TestClient, tournament_id: int, data_source: None
):
    response = http.post(
        f'/player-bulk-add/{EVENT_ID}',
        data={'players': picks('1')},
        follow_redirects=False,
    )
    assert response.headers['location'].endswith('/error/400')
    assert not EVENT.tournament().tournament_players


TEAM_EVENT = EventUnderTest('test-player-bulk-add-teams', 'Teams')


@pytest.fixture
def team_id() -> Iterator[int]:
    """A team of a tournament whose rosters hold two players, holding one."""
    TEAM_EVENT.create(
        event={'event_type': EventType.TEAM},
        tournament={
            'team_player_count': 1,
            'roster_max_size': 2,
            'pairing': 'TEAM_ROUND_ROBIN_BERGER',
        },
    )
    tournament = TEAM_EVENT.tournament()
    with EventDatabase(TEAM_EVENT.id, write=True) as database:
        team_id = database.add_stored_team(
            StoredTeam(id=None, name='Team A', tournament_id=tournament.id)
        )
        database.add_stored_player(
            StoredPlayer(id=None, last_name='MEMBER', team_id=team_id, team_index=0)
        )
    yield team_id
    TEAM_EVENT.delete()


@pytest.mark.unit
def test_the_players_picked_join_the_team_while_it_has_room(
    http: TestClient, team_id: int, data_source: None
):
    response = http.post(
        f'/player-bulk-add/{TEAM_EVENT.id}',
        data={'team_id': str(team_id), 'players': picks('1', '2')},
    )
    assert response.status_code == 200
    assert '1 player added.' in response.text
    assert 'team [Team A] is full' in response.text
    team = TEAM_EVENT.load().teams_by_id[team_id]
    assert last_names(team.players) == ['ALPHA', 'MEMBER']


@pytest.fixture
def searched() -> Iterator[AsyncMock]:
    """A data source finding the players of FOUND whatever is searched."""
    search = AsyncMock(
        side_effect=lambda *_args: [replace(player) for player in FOUND.values()]
    )
    fake = SimpleNamespace(
        id=SOURCE_ID,
        is_available=True,
        search_player=search,
        search_first_players=AsyncMock(return_value=None),
        info_or_warning_message=('', False),
        player_search_result_template='/admin/players/national_search_result.html',
        get_player_source_id=lambda stored_player: stored_player.last_name,
    )
    with (
        patch.object(
            DataSourceManager, 'get_object', lambda _manager, _data_source_id: fake
        ),
        patch.object(
            SearchFilterManager,
            'get_filters_by_datasource',
            return_value={
                SOURCE_ID: [
                    'club_filter',
                    'gender_filter',
                    'category_filter',
                    'ffe_licence_filter',
                ]
            },
        ),
    ):
        yield search


def search(http: TestClient, **params: str) -> Any:
    return http.get(
        f'/search-player/{EVENT_ID}',
        params={'data_source_id': SOURCE_ID, 'search': ''} | params,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    'filters', [{'club_filter': 'Club X'}, {'gender_filter': 'F'}], ids=str
)
def test_a_filter_lists_its_players_without_a_word_to_search(
    http: TestClient, tournament_id: int, searched: AsyncMock, filters: dict
):
    response = search(http, usage='bulk', filters=json.dumps(filters))
    assert response.status_code == 200
    assert searched.called
    assert 'BRAVO' in response.text


@pytest.mark.unit
def test_nothing_is_searched_without_words_or_filters(
    http: TestClient, tournament_id: int, searched: AsyncMock
):
    response = search(http, usage='bulk')
    assert response.status_code == 200
    assert not searched.called
    assert 'Type a name or set a filter to list players.' in response.text


@pytest.mark.unit
def test_a_single_player_search_needs_words_even_with_a_filter(
    http: TestClient, tournament_id: int, searched: AsyncMock
):
    response = search(http, filters=json.dumps({'club_filter': 'Club X'}))
    assert response.status_code == 200
    assert not searched.called


@pytest.mark.unit
def test_the_players_already_entered_are_marked(
    http: TestClient, tournament_id: int, searched: AsyncMock, data_source: None
):
    http.post(
        f'/player-bulk-add/{EVENT_ID}/{tournament_id}', data={'players': picks('2')}
    )
    response = search(http, usage='bulk', search='x', tournament_id=str(tournament_id))
    assert response.status_code == 200
    assert response.text.count('Already entered') == 1
    assert response.text.count('bulk-add-result"') == 2


@pytest.mark.unit
def test_a_filter_of_another_data_source_lists_nothing(
    http: TestClient, tournament_id: int, searched: AsyncMock
):
    """The filters of every data source are sent, those the data source
    searched does not have included."""
    with patch.object(
        SearchFilterManager,
        'get_filters_by_datasource',
        return_value={SOURCE_ID: ['gender_filter']},
    ):
        response = search(
            http, usage='bulk', filters=json.dumps({'club_filter': 'Club X'})
        )
    assert response.status_code == 200
    assert not searched.called


@pytest.mark.unit
@pytest.mark.parametrize(
    'filters', [{'club_filter': '  '}, {'category_filter': []}], ids=str
)
def test_a_blank_filter_lists_nothing(
    http: TestClient, tournament_id: int, searched: AsyncMock, filters: dict
):
    response = search(http, usage='bulk', filters=json.dumps(filters))
    assert response.status_code == 200
    assert not searched.called


@pytest.mark.unit
def test_a_player_no_longer_found_does_not_stop_the_others(
    http: TestClient, tournament_id: int, data_source: None
):
    gone = json.dumps([SOURCE_ID, 'gone', 'GONE Gus'])
    response = http.post(
        f'/player-bulk-add/{EVENT_ID}/{tournament_id}',
        data={'players': [*picks('1'), gone]},
    )
    assert response.status_code == 200
    assert '1 player added.' in response.text
    assert 'GONE Gus (no longer found in the data source)' in response.text
    assert last_names(EVENT.tournament().tournament_players) == ['ALPHA']


@pytest.mark.unit
def test_a_data_source_is_read_once_for_all_its_players(
    http: TestClient, tournament_id: int, fetch_players: AsyncMock
):
    http.post(
        f'/player-bulk-add/{EVENT_ID}/{tournament_id}',
        data={'players': picks('1', '2', '3')},
    )
    fetch_players.assert_called_once()
    assert fetch_players.call_args.args[0] == ['1', '2', '3']


@pytest.mark.unit
def test_the_players_of_a_data_source_that_fails_are_reported(
    http: TestClient, tournament_id: int, fetch_players: AsyncMock
):
    fetch_players.side_effect = SharlyChessException('down')
    response = http.post(
        f'/player-bulk-add/{EVENT_ID}/{tournament_id}',
        data={'players': picks('1')},
    )
    assert response.status_code == 200
    assert 'ALPHA (the data source could not be reached)' in response.text
    assert not EVENT.tournament().tournament_players


@pytest.mark.unit
def test_namesakes_are_not_added_together_to_a_team_event(
    http: TestClient, team_id: int, fetch_players: AsyncMock
):
    """A player added on their own is refused when a player of the event has
    the same name, so two picked together are too."""

    async def namesakes(player_source_ids: list[str], *_args: Any) -> Any:
        return {
            key: replace(FOUND['1'], date_of_birth=date(2000 + int(key), 1, 1))
            for key in player_source_ids
        }

    fetch_players.side_effect = namesakes
    response = http.post(
        f'/player-bulk-add/{TEAM_EVENT.id}',
        data={
            'players': [
                json.dumps([SOURCE_ID, '1', 'ALPHA one']),
                json.dumps([SOURCE_ID, '2', 'ALPHA two']),
            ]
        },
    )
    assert response.status_code == 200
    assert 'ALPHA two (picked twice)' in response.text


@pytest.mark.unit
def test_a_filter_left_at_its_default_lists_nothing(
    http: TestClient, tournament_id: int, searched: AsyncMock
):
    """The licensed players alone are what the modal starts from, not a
    choice of players to list."""
    with patch.object(
        PlayerAdminController,
        '_bulk_default_filters',
        return_value={'ffe_licence_filter': 'B'},
    ):
        response = search(
            http, usage='bulk', filters=json.dumps({'ffe_licence_filter': 'B'})
        )
        assert not searched.called
        assert response.status_code == 200
        response = search(
            http, usage='bulk', filters=json.dumps({'ffe_licence_filter': 'A'})
        )
    assert searched.called


@pytest.mark.unit
def test_the_modal_opens_its_filters_on_their_bulk_defaults(
    http: TestClient, tournament_id: int
):
    with patch.object(
        PlayerAdminController,
        '_bulk_default_filters',
        return_value={'ffe_licence_filter': 'B'},
    ):
        response = http.get(f'/player-bulk-add-modal/{EVENT_ID}')
    assert response.status_code == 200
    assert 'var SEARCH_FILTERS_KEY = "bulkAddSearchFilters";' in response.text
    assert 'var DEFAULT_SEARCH_FILTERS = {"ffe_licence_filter": "B"};' in response.text
    assert 'collapse show filter-collapsable-container' in response.text
