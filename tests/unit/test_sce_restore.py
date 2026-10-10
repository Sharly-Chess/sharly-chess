"""What the Sharly-Chess.com plugin carries across a restoration.

A backup holds what the plugin had recorded when it was taken, which is
behind what it has since told the site: the identifier of a tournament
created there, a deletion it has not confirmed, the session opened with it.
"""

from datetime import datetime, timedelta
from unittest import TestCase

import pytest

from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredEvent, StoredPlayer
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce import SCEPlugin
from plugins.sce.sce_data import (
    SCEEventPluginData,
    SCEPlayerPluginData,
    SCETokens,
    SCETournamentPluginData,
)
from tests.test_config import TestUtils

EVENT_UNIQ_ID = 'test-sce-restore'
SCE_EVENT_ID = 'SCE-EVT'
SCE_TOURNAMENT_ID = 'SCE-T1'
SCE_PLAYER_ID = 'SCE-P1'


def event_plugin_data(stored_event: StoredEvent) -> SCEEventPluginData:
    return SCEEventPluginData.from_stored_value(
        stored_event.plugin_data.get(PLUGIN_NAME, {})
    )


@pytest.mark.unit
class TestWhatIsCarriedAcrossARestoration(TestCase):
    def setUp(self) -> None:
        super().setUp()
        TestUtils.create_event(EVENT_UNIQ_ID)
        TestUtils.create_tournament(EVENT_UNIQ_ID, 'T1')
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            tournament_id = database.load_stored_tournaments()[0].id
            assert tournament_id is not None
            self.player_id = database.add_stored_player(
                StoredPlayer(id=None, last_name='LOCAL', first_name='Player')
            )
        self.tournament_id = tournament_id

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_UNIQ_ID)
        super().tearDown()

    @staticmethod
    def restore(previous: StoredEvent | None) -> StoredEvent:
        """Runs what the plugin does after the event has been replaced, and
        gives back the event as it stands afterwards."""
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            SCEPlugin().on_event_restored(
                event_database=database, previous_stored_event=previous
            )
        with EventDatabase(EVENT_UNIQ_ID) as database:
            return database.load_stored_event()

    def linked_event(
        self,
        deleted_player_ids: list[str] | None = None,
        tournament_sce_id: str | None = SCE_TOURNAMENT_ID,
        player_sce_id: str | None = SCE_PLAYER_ID,
    ) -> StoredEvent:
        """The event as it stood before being replaced, linked to the site."""
        with EventDatabase(EVENT_UNIQ_ID) as database:
            stored_event = database.load_stored_event()
        stored_event.plugin_data[PLUGIN_NAME] = SCEEventPluginData(
            id=SCE_EVENT_ID,
            slug='the-event',
            organiser_slug='the-organiser',
            tokens=SCETokens(
                access_token='ACCESS',
                refresh_token='REFRESH',
                expires_at=datetime.now() + timedelta(hours=1),
            ),
            deleted_player_ids=deleted_player_ids or [],
        ).to_stored_value()
        stored_event.enabled_plugins = [PLUGIN_NAME]
        for stored_tournament in stored_event.stored_tournaments:
            stored_tournament.plugin_data[PLUGIN_NAME] = SCETournamentPluginData(
                id=tournament_sce_id
            ).to_stored_value()
        for stored_player in stored_event.stored_players:
            stored_player.plugin_data[PLUGIN_NAME] = SCEPlayerPluginData(
                id=player_sce_id
            ).to_stored_value()
        return stored_event

    def test_the_link_and_the_session_are_carried_over(self) -> None:
        """A backup taken before the event was linked would leave it unlinked,
        and one taken before the last sign-in would ask for another."""
        restored = self.restore(self.linked_event())

        plugin_data = event_plugin_data(restored)
        assert plugin_data.id == SCE_EVENT_ID
        assert plugin_data.slug == 'the-event'
        assert plugin_data.organiser_slug == 'the-organiser'
        assert plugin_data.tokens is not None
        assert plugin_data.tokens.access_token == 'ACCESS'
        assert PLUGIN_NAME in restored.enabled_plugins

    def test_a_deletion_still_owed_to_the_site_is_carried_over(self) -> None:
        """A deletion the site has not confirmed is owed to it whichever state
        the event is in, or the registration stays there for good."""
        restored = self.restore(self.linked_event(deleted_player_ids=['SCE-GONE']))

        assert event_plugin_data(restored).deleted_player_ids == ['SCE-GONE']

    def test_a_tournament_registered_after_the_backup_keeps_its_identifier(
        self,
    ) -> None:
        """Without it the next upload opens a second tournament on the site."""
        restored = self.restore(self.linked_event())

        stored_tournament = restored.stored_tournaments[0]
        plugin_data = SCETournamentPluginData.from_stored_value(
            stored_tournament.plugin_data.get(PLUGIN_NAME, {})
        )
        assert plugin_data.id == SCE_TOURNAMENT_ID

    def test_a_player_registered_after_the_backup_keeps_their_registration(
        self,
    ) -> None:
        """A player without their registration is created again on the site,
        which answers that they are already there."""
        restored = self.restore(self.linked_event())

        stored_player = restored.stored_players[0]
        plugin_data = SCEPlayerPluginData.from_stored_value(
            stored_player.plugin_data.get(PLUGIN_NAME, {})
        )
        assert plugin_data.id == SCE_PLAYER_ID

    def test_what_the_backup_holds_itself_is_left_alone(self) -> None:
        """The backup is the state being restored: an identifier it carries is
        the one to keep."""
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            stored_tournament = database.load_stored_tournaments()[0]
            stored_tournament.plugin_data[PLUGIN_NAME] = SCETournamentPluginData(
                id='SCE-FROM-THE-BACKUP'
            ).to_stored_value()
            database.update_stored_tournament(stored_tournament)

        restored = self.restore(self.linked_event())

        plugin_data = SCETournamentPluginData.from_stored_value(
            restored.stored_tournaments[0].plugin_data.get(PLUGIN_NAME, {})
        )
        assert plugin_data.id == 'SCE-FROM-THE-BACKUP'

    def test_an_event_that_was_never_linked_is_left_alone(self) -> None:
        with EventDatabase(EVENT_UNIQ_ID) as database:
            previous = database.load_stored_event()

        restored = self.restore(previous)

        # Never linked reads as an empty identifier, not as a missing one.
        assert not event_plugin_data(restored).id
        assert PLUGIN_NAME not in restored.enabled_plugins

    def test_an_event_that_could_not_be_read_carries_nothing(self) -> None:
        """Restoring is the way out of a damaged event, which has nothing to
        give."""
        restored = self.restore(None)

        assert not event_plugin_data(restored).id


@pytest.mark.unit
class TestWhatTheUserIsTold(TestCase):
    def setUp(self) -> None:
        super().setUp()
        TestUtils.create_event(EVENT_UNIQ_ID)

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_UNIQ_ID)
        super().tearDown()

    def stored_event(self, linked: bool) -> StoredEvent:
        with EventDatabase(EVENT_UNIQ_ID) as database:
            stored_event = database.load_stored_event()
        if linked:
            stored_event.plugin_data[PLUGIN_NAME] = SCEEventPluginData(
                id=SCE_EVENT_ID
            ).to_stored_value()
        return stored_event

    def test_a_linked_event_is_restored_on_one_side_only(self) -> None:
        warning = SCEPlugin().get_event_restore_warning(
            stored_event=self.stored_event(linked=True)
        )

        assert warning is not None
        assert 'rolls back the rounds and the results' in warning
        assert 'It does not roll back the players' in warning

    def test_a_copy_is_told_to_be_connected_to_nothing(self) -> None:
        warning = SCEPlugin().get_event_copy_warning(
            stored_event=self.stored_event(linked=True)
        )

        assert warning is not None
        assert 'not linked' in warning

    def test_an_event_of_its_own_is_warned_about_nothing(self) -> None:
        stored_event = self.stored_event(linked=False)

        assert SCEPlugin().get_event_restore_warning(stored_event=stored_event) is None
        assert SCEPlugin().get_event_copy_warning(stored_event=stored_event) is None
