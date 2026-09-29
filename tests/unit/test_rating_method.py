"""The tournament rating of a player under each rating method: the TRF26
methods rank a player without a rating from the lists they name at 0 (HBFN
also compares the estimated rating), the others fall back to the estimated
rating."""

from unittest import TestCase

import pytest

from data.loader import EventLoader
from data.player import TournamentPlayer
from data.tournament import Tournament
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTournament,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import PlayerRatingType, RatingMethod, TournamentRating
from utils.types import PlayerRating, PlayerRatingAndType

EVENT_ID = 'test-rating-method'
PLAYER_ID = 1001

FIDE = PlayerRatingType.FIDE
NATIONAL = PlayerRatingType.NATIONAL
ESTIMATED = PlayerRatingType.ESTIMATED


@pytest.mark.unit
class RatingMethodTestCase(TestCase):
    enabled_plugins: tuple[str, ...] = ()

    def setUp(self):
        TestUtils.create_event(
            EVENT_ID, overrides={'enabled_plugins': list(self.enabled_plugins)}
        )

    def tearDown(self):
        TestUtils.delete_event(EVENT_ID)

    def _rating(
        self, rating_method: RatingMethod, rating: PlayerRating
    ) -> PlayerRatingAndType:
        self.event = EventLoader().load_event(EVENT_ID)
        self.event.stored_event.stored_players = [
            StoredPlayer(
                id=PLAYER_ID,
                last_name='DOE',
                year_of_birth=1980,
                ratings={TournamentRating.STANDARD.value: rating.stored_value},
            )
        ]
        tournament = Tournament(
            self.event,
            StoredTournament(
                id=1,
                name='Rating method',
                rating=TournamentRating.STANDARD.value,
                rating_method=rating_method.value,
                stored_tournament_players=[
                    StoredTournamentPlayer(tournament_id=1, player_id=PLAYER_ID)
                ],
            ),
        )
        tournament_player: TournamentPlayer = tournament.tournament_players_by_id[
            PLAYER_ID
        ]
        return PlayerRatingAndType(
            tournament_player.rating, tournament_player.rating_type
        )


class CoreRatingMethodTestCase(RatingMethodTestCase):
    def test_each_method_picks_its_rating(self):
        all_ratings = PlayerRating(fide=1800, national=1900, estimated=2000)
        national_only = PlayerRating(national=1900, estimated=2000)
        fide_only = PlayerRating(fide=1800, estimated=2000)
        estimated_only = PlayerRating(estimated=2000)
        for rating_method, rating, expected in (
            (RatingMethod.FIDE, all_ratings, (1800, FIDE)),
            (RatingMethod.FIDE, national_only, (0, FIDE)),
            (RatingMethod.NATIONAL, all_ratings, (1900, NATIONAL)),
            (RatingMethod.NATIONAL, fide_only, (0, NATIONAL)),
            (RatingMethod.FIDE_NATIONAL, all_ratings, (1800, FIDE)),
            (RatingMethod.FIDE_NATIONAL, national_only, (1900, NATIONAL)),
            (RatingMethod.FIDE_NATIONAL, estimated_only, (0, FIDE)),
            (RatingMethod.NATIONAL_FIDE, all_ratings, (1900, NATIONAL)),
            (RatingMethod.NATIONAL_FIDE, fide_only, (1800, FIDE)),
            (RatingMethod.NATIONAL_FIDE, estimated_only, (0, NATIONAL)),
            (RatingMethod.HIGHEST, all_ratings, (2000, ESTIMATED)),
            (
                RatingMethod.HIGHEST,
                PlayerRating(fide=1800, national=1700),
                (1800, FIDE),
            ),
            (RatingMethod.HIGHEST, PlayerRating(), (0, FIDE)),
            (RatingMethod.FIDE_ESTIMATED, national_only, (2000, ESTIMATED)),
            (RatingMethod.NATIONAL_ESTIMATED, fide_only, (2000, ESTIMATED)),
            (RatingMethod.FIDE_NATIONAL_ESTIMATED, national_only, (1900, NATIONAL)),
            (RatingMethod.FIDE_NATIONAL_ESTIMATED, estimated_only, (2000, ESTIMATED)),
            (RatingMethod.NATIONAL_FIDE_ESTIMATED, fide_only, (1800, FIDE)),
            (RatingMethod.NATIONAL_FIDE_ESTIMATED, estimated_only, (2000, ESTIMATED)),
            (RatingMethod.FIDE_ESTIMATED, PlayerRating(), (0, FIDE)),
        ):
            with self.subTest(rating_method=rating_method, rating=str(rating)):
                self.assertEqual(
                    self._rating(rating_method, rating),
                    PlayerRatingAndType(*expected),
                )


class FFERatingMethodTestCase(RatingMethodTestCase):
    enabled_plugins = ('ffe',)

    def test_the_ffe_ranks_on_fide_then_national_then_estimated(self):
        self.assertEqual(
            self._rating(RatingMethod.NATIONAL, PlayerRating(fide=1800, national=1900)),
            PlayerRatingAndType(1800, FIDE),
        )
        self.assertEqual(
            self._rating(RatingMethod.FIDE, PlayerRating(national=1900)),
            PlayerRatingAndType(1900, NATIONAL),
        )

    def test_the_ffe_gives_an_unrated_player_a_default_rating(self):
        self.assertEqual(
            self._rating(RatingMethod.FIDE, PlayerRating()),
            PlayerRatingAndType(1399, ESTIMATED),
        )
