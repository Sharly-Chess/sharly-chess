"""The ratings shown for a player not yet entered — a search result or a
row of an import — when the list rates them at another cadence than the
tournaments of the event: they are ranked on the estimate, the player
belonging to no tournament."""

import pytest

from data.loader import EventLoader
from data.player import Player
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer
from tests.test_config import TestUtils
from utils.enum import Cadence, PlayerRatingType
from utils.types import PlayerRating

EVENT_ID = 'test-player-not-entered-ratings'


@pytest.fixture(autouse=True)
def delete_event():
    yield
    if EventDatabase(EVENT_ID).exists():
        TestUtils.delete_event(EVENT_ID)


@pytest.mark.unit
def test_a_player_not_entered_is_ranked_on_the_estimate():
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(
        EVENT_ID, 'Standard', overrides={'cadence': Cadence.STANDARD.value}
    )
    event = EventLoader().load_event(EVENT_ID)
    player = Player(
        event,
        StoredPlayer(
            id=None,
            last_name='DOE',
            year_of_birth=1980,
            ratings={Cadence.RAPID.value: PlayerRating(fide=1500).stored_value},
        ),
    )
    [(cadence, rating)] = player.event_ratings
    assert (cadence, rating.value, rating.type) == (
        Cadence.STANDARD,
        event.prescribed_rating(Cadence.STANDARD, player, player.category, None),
        PlayerRatingType.ESTIMATED,
    )
