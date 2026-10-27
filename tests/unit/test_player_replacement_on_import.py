"""Players replaced by an import that deletes the existing ones: the
imported players identified as the same person keep the plugin data of
the players they replace, and the others are reported as deleted."""

from unittest import TestCase

import pytest

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTournamentPlayer,
)
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_data import SCEPlayerPluginData
from plugins.sce.utils import SCEUtils

from tests.test_config import TestUtils


EVENT_UNIQ_ID = 'test-player-replacement-on-import'


def _enable_sce() -> None:
    with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
        stored_event = database.load_stored_event()
        stored_event.enabled_plugins = [PLUGIN_NAME]
        database.update_stored_event(stored_event)


def _add_player(
    tournament_ids: list[int],
    last_name: str,
    fide_id: int | None = None,
    sce_player_id: str | None = None,
) -> int:
    plugin_data = (
        {PLUGIN_NAME: SCEPlayerPluginData(id=sce_player_id).to_stored_value()}
        if sce_player_id
        else {}
    )
    with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
        player_id = database.add_stored_player(
            StoredPlayer(
                id=None,
                last_name=last_name,
                first_name='Player',
                fide_id=fide_id,
                federation='FRA',
                plugin_data=plugin_data,
            )
        )
        for tournament_id in tournament_ids:
            database.add_stored_tournament_player(
                StoredTournamentPlayer(player_id=player_id, tournament_id=tournament_id)
            )
    return player_id


@pytest.mark.unit
class TestPlayerReplacementOnImport(TestCase):
    def setUp(self):
        super().setUp()
        TestUtils.create_event(EVENT_UNIQ_ID)
        self.tournament_id = TestUtils.create_tournament(EVENT_UNIQ_ID, 'T1').id
        self.other_tournament_id = TestUtils.create_tournament(EVENT_UNIQ_ID, 'T2').id

    def tearDown(self):
        TestUtils.delete_event(EVENT_UNIQ_ID)
        super().tearDown()

    def test_players_replaced_by_import_excludes_shared_players(self):
        exclusive_id = _add_player([self.tournament_id], 'Exclusive')
        _add_player([self.tournament_id, self.other_tournament_id], 'Shared')
        event = EventLoader().load_event(EVENT_UNIQ_ID)
        tournament = event.tournaments_by_id[self.tournament_id]
        self.assertEqual(
            [player.id for player in event.players_replaced_by_import(tournament)],
            [exclusive_id],
        )

    def test_players_replaced_by_import_at_event_level(self):
        _add_player([self.tournament_id], 'First')
        _add_player([self.other_tournament_id], 'Second')
        event = EventLoader().load_event(EVENT_UNIQ_ID)
        self.assertEqual(len(event.players_replaced_by_import(None)), 2)

    def test_same_player_keeps_link_and_others_are_deleted(self):
        _enable_sce()
        _add_player([self.tournament_id], 'Kept', fide_id=1001, sce_player_id='K')
        _add_player([self.tournament_id], 'Gone', fide_id=1002, sce_player_id='G')
        event = EventLoader().load_event(EVENT_UNIQ_ID)
        tournament = event.tournaments_by_id[self.tournament_id]
        kept = StoredPlayer(id=None, last_name='Kept', fide_id=1001)
        new = StoredPlayer(id=None, last_name='New', fide_id=1003)

        dropped_players = event.carry_over_reimported_players(
            event.players_replaced_by_import(tournament), [kept, new]
        )
        event.notify_players_deleted(dropped_players)

        self.assertEqual([player.last_name for player in dropped_players], ['Gone'])
        self.assertEqual(kept.plugin_data[PLUGIN_NAME]['id'], 'K')
        self.assertNotIn(PLUGIN_NAME, new.plugin_data)
        event = EventLoader().load_event(EVENT_UNIQ_ID)
        self.assertEqual(
            SCEUtils.get_event_plugin_data(event).deleted_player_ids, ['G']
        )

    def test_imported_plugin_data_is_not_overwritten(self):
        _add_player([self.tournament_id], 'Kept', fide_id=1001, sce_player_id='OLD')
        event = EventLoader().load_event(EVENT_UNIQ_ID)
        tournament = event.tournaments_by_id[self.tournament_id]
        kept = StoredPlayer(
            id=None,
            last_name='Kept',
            fide_id=1001,
            plugin_data={PLUGIN_NAME: {'id': 'NEW'}},
        )

        event.carry_over_reimported_players(
            event.players_replaced_by_import(tournament), [kept]
        )

        self.assertEqual(kept.plugin_data[PLUGIN_NAME]['id'], 'NEW')
