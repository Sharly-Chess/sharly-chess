"""The rating of the players no list rates and for whom the arbiter typed
none: the one a plugin prescribes, else the tournament's, else the
event's, 1400 unless set."""

import pytest

from data.loader import EventLoader
from data.rating_sequences import DEFAULT_UNRATED_RATING
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTournament,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import Cadence, PlayerRatingType
from utils.types import PlayerRating

EVENT_ID = 'test-unrated-rating'
PLAYER_ID = 1001


def _unrated_player_rating(
    federation: str,
    event_unrated_rating: int | None = None,
    tournament_unrated_rating: int | None = None,
    manual: int | None = None,
):
    TestUtils.create_event(
        EVENT_ID,
        overrides={
            'federation': federation,
            'unrated_rating': event_unrated_rating,
            'enabled_plugins': ['ffe'] if federation == 'FRA' else [],
        },
    )
    event = EventLoader().load_event(EVENT_ID)
    event.stored_event.stored_players.append(
        StoredPlayer(
            id=PLAYER_ID,
            last_name='DOE',
            year_of_birth=1980,
            ratings={Cadence.STANDARD.value: PlayerRating(manual=manual).stored_value},
        )
    )
    tournament = Tournament(
        event,
        StoredTournament(
            id=1,
            name='Unrated',
            cadence=Cadence.STANDARD.value,
            unrated_rating=tournament_unrated_rating,
            stored_tournament_players=[
                StoredTournamentPlayer(tournament_id=1, player_id=PLAYER_ID)
            ],
        ),
    )
    return tournament.tournament_players_by_id[PLAYER_ID].tournament_rating


@pytest.fixture(autouse=True)
def delete_event():
    yield
    if EventDatabase(EVENT_ID).exists():
        TestUtils.delete_event(EVENT_ID)


@pytest.mark.unit
def test_an_unrated_player_is_ranked_on_the_default():
    rating = _unrated_player_rating('ENG')
    assert (rating.value, rating.type, rating.prescribed) == (
        DEFAULT_UNRATED_RATING,
        PlayerRatingType.ESTIMATED,
        True,
    )


@pytest.mark.unit
def test_the_event_and_the_tournament_set_the_rating_of_unrated_players():
    assert _unrated_player_rating('ENG', event_unrated_rating=1000).value == 1000
    TestUtils.delete_event(EVENT_ID)
    assert (
        _unrated_player_rating(
            'ENG', event_unrated_rating=1000, tournament_unrated_rating=0
        ).value
        == 0
    )


@pytest.mark.unit
def test_a_typed_value_comes_before_the_rating_of_unrated_players():
    rating = _unrated_player_rating('ENG', manual=1550)
    assert (rating.value, rating.prescribed) == (1550, False)


@pytest.mark.unit
def test_a_plugin_prescribes_the_rating_in_place_of_the_event():
    rating = _unrated_player_rating(
        'FRA', event_unrated_rating=1000, tournament_unrated_rating=1100
    )
    assert (rating.value, rating.prescribed) == (1399, True)
    assert EventLoader().load_event(EVENT_ID).prescribed_rating_rule


@pytest.mark.unit
def test_existing_events_keep_ranking_unrated_players_at_zero(tmp_path):
    from database.sqlite.event.migrations.m116_unrated_rating import Migration
    from database.sqlite.sqlite_database import SQLiteDatabase

    for has_tournament, expected in ((True, 0), (False, None)):
        file = tmp_path / f'event-{has_tournament}.db'
        SQLiteDatabase(file, write=True)._create(
            'CREATE TABLE info (name TEXT);'
            'CREATE TABLE tournament (id INTEGER PRIMARY KEY)'
        )
        with SQLiteDatabase(file, write=True) as database:
            database.execute("INSERT INTO info (name) VALUES ('Event')")
            if has_tournament:
                database.execute('INSERT INTO tournament (id) VALUES (1)')
            Migration(database).forward()  # type: ignore[arg-type]
            database.execute('SELECT unrated_rating FROM info')
            assert database.fetchone()['unrated_rating'] == expected
