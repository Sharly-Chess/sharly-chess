import pytest
from unittest import TestCase

from data.loader import EventLoader
from data.player import PlayerProfileLink
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer
from tests.test_config import TestUtils

EVENT_ID = 'test-player-profile-links'


@pytest.mark.unit
class PlayerProfileLinksTestCase(TestCase):
    def setUp(self):
        super().setUp()
        TestUtils.create_event(EVENT_ID)
        self.event = EventLoader().load_event(EVENT_ID)

    def tearDown(self):
        TestUtils.delete_event(EVENT_ID)
        super().tearDown()

    def _player_with_fide_id(self, fide_id: int | None):
        with EventDatabase(EVENT_ID, write=True) as database:
            player_id = database.add_stored_player(
                StoredPlayer(
                    id=None,
                    last_name='DOE',
                    first_name='John',
                    fide_id=fide_id,
                )
            )
        self.event = EventLoader().load_event(EVENT_ID)
        return self.event.players_by_id[player_id]

    def test_fide_link_is_offered_when_the_player_has_an_id(self):
        player = self._player_with_fide_id(653055225)
        self.assertEqual(
            player.profile_links,
            [
                PlayerProfileLink(
                    label='FIDE 653055225',
                    url='https://ratings.fide.com/profile/653055225',
                )
            ],
        )

    def test_no_link_without_a_fide_id(self):
        player = self._player_with_fide_id(None)
        self.assertEqual(player.profile_links, [])
