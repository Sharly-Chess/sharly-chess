"""The players tab and the records of one player, over HTTP."""

from collections.abc import Iterator
from datetime import date

import pytest
from litestar.testing import TestClient

from data.player import TournamentPlayer
from utils.types import PlayerRating
from data.tournament import Tournament
from tests.unit.http.events import EventUnderTest
from utils.enum import PlayerGender, PlayerTitle, TournamentRating

EVENT_ID = 'test-players-http'
TOURNAMENT_NAME = 'test-players-http-tournament'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


@pytest.fixture
def tournament() -> Iterator[Tournament]:
    EVENT.create(json_file='tec-swiss')
    yield EVENT.tournament()
    EVENT.delete()


def first_player(tournament: Tournament) -> TournamentPlayer:
    return sorted(tournament.tournament_players, key=lambda player: player.id)[0]


@pytest.mark.unit
def test_the_search_box_narrows_the_table_to_one_player(
    http: TestClient, tournament: Tournament
):
    """What is typed in the box is kept in the session, so the table
    comes back narrowed on every later render too."""
    player = first_player(tournament)
    response = http.get(
        f'/event/{EVENT_ID}/players/search', params={'search': player.last_name}
    )
    assert response.status_code == 200
    assert player.last_name in response.text
    others = [
        other
        for other in tournament.tournament_players
        if other.last_name != player.last_name
    ]
    assert others
    assert not any(other.last_name in response.text for other in others)
    cleared = http.get(f'/event/{EVENT_ID}/players/clear-filters')
    assert cleared.status_code == 200
    assert others[0].last_name in cleared.text


@pytest.mark.unit
def test_the_tab_offers_an_export_per_format(http: TestClient, tournament: Tournament):
    response = http.get(f'/event/{EVENT_ID}/players')
    assert response.status_code == 200
    assert f'/event-export-players/{EVENT_ID}/' in response.text


@pytest.mark.unit
def test_the_table_is_sorted_by_a_column(http: TestClient, tournament: Tournament):
    response = http.get(f'/event/{EVENT_ID}/players/sort/last_name')
    assert response.status_code == 200


@pytest.mark.unit
def test_a_withdrawn_player_is_taken_off_the_list(
    http: TestClient, tournament: Tournament
):
    """Withdrawing is the arbiter's answer to a player who leaves during
    the tournament: they stop counting as present, and any round still to
    come becomes a bye. Returning puts them back."""
    player = first_player(tournament)
    response = http.patch(f'/records/withdraw-player/{EVENT_ID}/{player.id}')
    assert response.status_code == 200
    assert not first_player(EVENT.tournament()).check_in

    returned = http.patch(f'/records/return-player/{EVENT_ID}/{player.id}')
    assert returned.status_code == 200
    assert first_player(EVENT.tournament()).check_in


@pytest.mark.unit
def test_a_player_who_has_played_is_not_deleted(
    http: TestClient, tournament: Tournament
):
    """Deleting them would leave their opponents' games pointing at
    nobody, so the arbiter is told to withdraw them instead."""
    player = first_player(tournament)
    before = len(tournament.tournament_players)
    response = http.delete(f'/player-delete/{EVENT_ID}/{player.id}')
    assert response.status_code == 200
    assert 'has pairings in tournament' in response.text
    assert len(EVENT.tournament().tournament_players) == before


@pytest.mark.unit
def test_a_player_who_has_not_played_is_deleted(
    http: TestClient, tournament: Tournament
):
    before = len(tournament.tournament_players)
    created = http.post(
        f'/player-create/{EVENT_ID}',
        data={
            'federation': 'FRA',
            'gender': '',
            'title': '',
            'tournament_id': str(tournament.id),
            'last_name': 'Latecomer',
        },
    )
    assert created.status_code == 200
    entered = EVENT.tournament().tournament_players
    assert len(entered) == before + 1
    latecomer = next(player for player in entered if player.last_name == 'LATECOMER')
    response = http.delete(f'/player-delete/{EVENT_ID}/{latecomer.id}')
    assert response.status_code == 200
    assert len(EVENT.tournament().tournament_players) == before


@pytest.mark.unit
@pytest.mark.parametrize('action', ['update', 'clone'])
def test_the_player_modal_opens_for_every_action(
    http: TestClient, tournament: Tournament, action: str
):
    response = http.get(
        f'/player-modal/{action}/{EVENT_ID}/{first_player(tournament).id}'
    )
    assert response.status_code == 200


@pytest.mark.unit
def test_a_player_who_is_not_there_has_no_row(http: TestClient, tournament: Tournament):
    response = http.get(f'/player-row/{EVENT_ID}/9999', follow_redirects=False)
    assert response.status_code == 302
    assert response.headers['location'].endswith('/error/404')


FULL_PLAYER = {
    'last_name': 'doe',
    'first_name': 'john',
    'date_of_birth': '2000-10-30',
    'gender': str(PlayerGender.MAN.value),
    'club': 'SC Club',
    'federation': 'FRA',
    'fixed': '100',
    'standard_rating_estimated': '1000',
    'rapid_rating_national': '1500',
    'blitz_rating_fide': '2000',
    'blitz_rating_k': '20',
    'title': str(PlayerTitle.GRANDMASTER.value),
    'mail': 'john.doe@sharly-chess.com',
    'owed': '10',
    'paid': '20',
    'comment': 'Comment',
}


@pytest.mark.unit
def test_a_player_is_stored_as_the_form_was_filled_in(
    http: TestClient, tournament: Tournament
):
    """Every field of the entry form, read back from the event it was
    written to."""
    response = http.post(
        f'/player-create/{EVENT_ID}',
        data=FULL_PLAYER | {'tournament_id': str(tournament.id)},
    )
    assert response.status_code == 200

    entered = next(
        player
        for player in EVENT.tournament().tournament_players
        if player.last_name == 'DOE'
    )
    assert entered.first_name == 'John'
    assert entered.date_of_birth == date(2000, 10, 30)
    assert entered.gender == PlayerGender.MAN
    assert entered.club.name == 'SC Club'
    assert entered.federation.name == 'FRA'
    assert entered.fixed == 100
    assert entered.ratings == {
        TournamentRating.STANDARD: PlayerRating(estimated=1000),
        TournamentRating.RAPID: PlayerRating(national=1500),
        TournamentRating.BLITZ: PlayerRating(fide=2000, k_factor=20),
    }
    assert entered.title == PlayerTitle.GRANDMASTER
    assert entered.mail == 'john.doe@sharly-chess.com'
    assert entered.owed == 10
    assert entered.paid == 20
    assert entered.comment == 'Comment'


@pytest.mark.unit
def test_a_player_is_renamed_and_then_removed(http: TestClient, tournament: Tournament):
    created = http.post(
        f'/player-create/{EVENT_ID}',
        data=FULL_PLAYER | {'tournament_id': str(tournament.id)},
    )
    assert created.status_code == 200
    entered = next(
        player
        for player in EVENT.tournament().tournament_players
        if player.last_name == 'DOE'
    )

    renamed = http.patch(
        f'/player-update/{EVENT_ID}/{entered.id}',
        data=FULL_PLAYER | {'tournament_id': str(tournament.id), 'last_name': 'hoe'},
    )
    assert renamed.status_code == 200
    assert [
        player.last_name
        for player in EVENT.tournament().tournament_players
        if player.id == entered.id
    ] == ['HOE']

    removed = http.delete(f'/player-delete/{EVENT_ID}/{entered.id}')
    assert removed.status_code == 200
    assert entered.id not in {
        player.id for player in EVENT.tournament().tournament_players
    }
