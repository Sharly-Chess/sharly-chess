"""A rapid tournament of an FFE event ranks a player the FFE list rates
only in rapid on that rating, whether it is a rating or an estimate."""

import pytest

from data.loader import EventLoader
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTournament,
    StoredTournamentPlayer,
)
from plugins.ffe.utils import ffe_list_ratings
from tests.test_config import TestUtils
from utils.enum import Cadence, PlayerRatingType
from utils.types import PlayerRatingAndType, RatingOrigin

EVENT_ID = 'test-ffe-rapid-rating'
PLAYER_ID = 1001
FFE_LIST = RatingOrigin('ffe', '2026-11-01')


@pytest.fixture(autouse=True)
def delete_event():
    yield
    if EventDatabase(EVENT_ID).exists():
        TestUtils.delete_event(EVENT_ID)


def _rapid_tournament_rating(
    list_ratings: dict[Cadence, tuple[int | None, PlayerRatingType]],
    year_of_birth: int,
) -> PlayerRatingAndType:
    """The rating a rapid tournament of an FFE event uses for a player
    entered from the FFE list."""
    TestUtils.create_event(
        EVENT_ID,
        overrides={'federation': 'FRA', 'enabled_plugins': ['ffe']},
    )
    event = EventLoader().load_event(EVENT_ID)
    event.stored_event.stored_players.append(
        StoredPlayer(
            id=PLAYER_ID,
            last_name='DOE',
            year_of_birth=year_of_birth,
            ratings=ffe_list_ratings(list_ratings, FFE_LIST, year_of_birth),
        )
    )
    tournament = Tournament(
        event,
        StoredTournament(
            id=1,
            name='Rapid',
            cadence=Cadence.RAPID.value,
            stored_tournament_players=[
                StoredTournamentPlayer(tournament_id=1, player_id=PLAYER_ID)
            ],
        ),
    )
    return tournament.tournament_players_by_id[PLAYER_ID].tournament_rating


@pytest.mark.unit
def test_a_player_with_only_an_ffe_rapid_rating_is_ranked_on_it():
    rating = _rapid_tournament_rating(
        {Cadence.RAPID: (1230, PlayerRatingType.NATIONAL)}, year_of_birth=2019
    )
    assert (rating.value, rating.type, rating.origin) == (
        1230,
        PlayerRatingType.NATIONAL,
        FFE_LIST,
    )


@pytest.mark.unit
def test_the_estimates_of_the_other_cadences_do_not_hide_the_rapid_rating():
    rating = _rapid_tournament_rating(
        {
            Cadence.STANDARD: (1299, PlayerRatingType.NATIONAL),
            Cadence.RAPID: (1230, PlayerRatingType.NATIONAL),
            Cadence.BLITZ: (799, PlayerRatingType.NATIONAL),
        },
        year_of_birth=2019,
    )
    assert (rating.value, rating.type) == (1230, PlayerRatingType.NATIONAL)


@pytest.mark.unit
def test_an_ffe_rapid_estimate_above_the_player_category_is_kept():
    """A U8 player the list gives 999 holds the estimate their club asked
    for, not one they outgrew: the plugin must not prescribe 799 instead."""
    rating = _rapid_tournament_rating(
        {Cadence.RAPID: (999, PlayerRatingType.NATIONAL)}, year_of_birth=2019
    )
    assert (rating.value, rating.type) == (999, PlayerRatingType.ESTIMATED)


@pytest.mark.unit
def test_an_outgrown_ffe_rapid_estimate_follows_the_player_category():
    """A U12 player the list still gives 799 outgrew that estimate: the
    plugin prescribes the estimate of their category."""
    rating = _rapid_tournament_rating(
        {Cadence.RAPID: (799, PlayerRatingType.NATIONAL)}, year_of_birth=2015
    )
    assert (rating.value, rating.prescribed) == (999, True)
