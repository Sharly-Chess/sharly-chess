"""What a synchronisation does with an event that has just been restored.

A backup moves the local side only: the site holds what it was told since,
and the next synchronisation settles the difference. These are the answers
the user is given before they restore — the rounds and the results roll
back, the players come back from the site — driven through `sync_event`
with the HTTP boundary mocked.
"""

from unittest import TestCase
from unittest.mock import MagicMock

import pytest

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer, StoredTournamentPlayer
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_data import (
    SCEEventPluginData,
    SCEPlayerPluginData,
    SCEPlayerSyncData,
    SCETournamentPluginData,
)
from plugins.sce.sce_session import SCESession
from tests.test_config import TestUtils

EVENT_UNIQ_ID = 'test-sce-restored-sync'
SCE_EVENT_ID = 'SCE-EVT'
SCE_TOURNAMENT_ID = 'SCE-T1'


def registration(
    sce_player_id: str,
    last_name: str = 'LOCAL',
    first_name: str = 'Player',
    rating: int | None = None,
    checked_in: bool = False,
) -> dict:
    """One registration as Sharly-Chess.com hands it over."""
    return {
        'id': sce_player_id,
        'last_name': last_name,
        'first_name': first_name,
        'year_of_birth': 1990,
        'fide_id': None,
        'national_id': None,
        'federation': 'FRA',
        'title': None,
        'club': None,
        'rating': rating,
        'rating_type': 'f' if rating else None,
        'phone_number': None,
        'comment': None,
        'gender': None,
        'checked_in': checked_in,
        'ffe_licence_type': None,
        'ffe_league': None,
        'fra_school': None,
    }


def event_data(registrations: list[dict]) -> dict:
    return {
        'id': SCE_EVENT_ID,
        'slug': 'test-event',
        'organiser_slug': 'test-org',
        'status': 'open',
        'age_categories': [],
        'age_category_base_date': None,
        'age_category_change_month': 1,
        'allow_multiple_tournament_registrations': True,
        'tournaments': [
            {
                'id': SCE_TOURNAMENT_ID,
                'name': 'T1',
                'registrations': registrations,
            }
        ],
    }


@pytest.mark.unit
class TestSynchronisingARestoredEvent(TestCase):
    def setUp(self) -> None:
        super().setUp()
        TestUtils.create_event(EVENT_UNIQ_ID)
        TestUtils.create_tournament(EVENT_UNIQ_ID, 'T1')
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            stored_event = database.load_stored_event()
            stored_event.plugin_data[PLUGIN_NAME] = SCEEventPluginData(
                id=SCE_EVENT_ID, slug='test-event', organiser_slug='test-org'
            ).to_stored_value()
            database.update_stored_event(stored_event)
            stored_tournament = database.load_stored_tournaments()[0]
            stored_tournament.plugin_data[PLUGIN_NAME] = SCETournamentPluginData(
                id=SCE_TOURNAMENT_ID
            ).to_stored_value()
            database.update_stored_tournament(stored_tournament)
            assert stored_tournament.id is not None
            self.tournament_id: int = stored_tournament.id

    def tearDown(self) -> None:
        EventLoader.unload_event(EVENT_UNIQ_ID)
        TestUtils.delete_event(EVENT_UNIQ_ID)
        super().tearDown()

    def add_restored_player(
        self,
        sce_player_id: str,
        last_name: str = 'LOCAL',
    ) -> int:
        """A player as a restored backup holds them: the state they were in
        when it was taken, which is the state last exchanged with the site."""
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            player_id = database.add_stored_player(
                StoredPlayer(
                    id=None,
                    last_name=last_name,
                    first_name='Player',
                    federation='FRA',
                    year_of_birth=1990,
                )
            )
            database.add_stored_tournament_player(
                StoredTournamentPlayer(
                    player_id=player_id, tournament_id=self.tournament_id
                )
            )
        event = EventLoader().load_event(EVENT_UNIQ_ID)
        player = next(
            tournament_player
            for tournament in event.tournaments
            for tournament_player in tournament.tournament_players
            if tournament_player.id == player_id
        )
        plugin_data = SCEPlayerPluginData(
            id=sce_player_id, last_sync_data=SCEPlayerSyncData.from_player(player)
        )
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            stored_player = next(
                stored
                for stored in database.load_stored_players()
                if stored.id == player_id
            )
            stored_player.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
            database.update_stored_player(stored_player)
        EventLoader.unload_event(EVENT_UNIQ_ID)
        return player_id

    def sync(self, registrations: list[dict]) -> list[dict]:
        """Runs a synchronisation against a site holding *registrations*, and
        gives back the operations sent to it."""
        event = EventLoader().load_event(EVENT_UNIQ_ID)
        session = SCESession(event)
        session._sync_tournament = MagicMock(return_value=True)  # type: ignore[method-assign]
        session._get_event_data = MagicMock(  # type: ignore[method-assign]
            return_value=event_data(registrations)
        )
        sent: list[dict] = []

        def run(request_function, *args, **kwargs):
            operations = getattr(request_function, 'keywords', {}).get('ops') or []
            sent.extend(operations)
            response = MagicMock()
            response.status_code = 207
            # The site answers one result per operation, in the order sent.
            response.json.return_value = {
                'results': [
                    {'status': 'ok', 'index': index, 'registration_id': 'SCE-NEW'}
                    for index, _ in enumerate(operations)
                ]
            }
            return response

        session._run_with_token_validation = MagicMock(side_effect=run)  # type: ignore[method-assign]
        session.new_check_ins_tournament_sce_ids = set()
        session.sync_event()
        EventLoader.unload_event(EVENT_UNIQ_ID)
        return sent

    def players(self) -> list[StoredPlayer]:
        with EventDatabase(EVENT_UNIQ_ID) as database:
            return database.load_stored_players()

    def test_a_player_registered_since_the_backup_comes_back(self) -> None:
        """The backup does not hold them, the site does: the synchronisation
        reads a registration with no player of its own and creates one."""
        sent = self.sync([registration('SCE-NEW', last_name='NEWCOMER')])

        assert [player.last_name for player in self.players()] == ['NEWCOMER']
        assert not sent

    def test_a_player_deleted_on_the_site_goes_again(self) -> None:
        """The backup holds them, the site does not: the site is the one that
        says who is registered."""
        self.add_restored_player('SCE-GONE', last_name='GONE')

        self.sync([])

        assert not self.players()

    def test_what_the_site_was_told_since_the_backup_comes_back(self) -> None:
        """The rounds and the results roll back, the players do not: what the
        site holds of a player is read as a change made there, and the restored
        value gives way to it."""
        self.add_restored_player('SCE-P1', last_name='BEFORE')

        self.sync([registration('SCE-P1', last_name='WHAT THE SITE HOLDS')])

        assert [player.last_name for player in self.players()] == [
            'WHAT THE SITE HOLDS'
        ]

    def test_a_change_made_after_restoring_is_sent_to_the_site(self) -> None:
        """What the restoration gives back is not pushed by itself, but a
        correction made over it is: the way out of the one above."""
        player_id = self.add_restored_player('SCE-P1', last_name='BEFORE')
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            stored_player = next(
                stored
                for stored in database.load_stored_players()
                if stored.id == player_id
            )
            stored_player.last_name = 'CORRECTED AGAIN'
            database.update_stored_player(stored_player)

        sent = self.sync([registration('SCE-P1', last_name='BEFORE')])

        assert [op['op'] for op in sent] == ['update']
        assert sent[0]['data']['last_name'] == 'CORRECTED AGAIN'
