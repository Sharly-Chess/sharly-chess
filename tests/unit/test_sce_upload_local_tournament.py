"""`SCESession.create_sce_tournament`: uploading a local tournament.

The tournament is created on Sharly-Chess.com and its players are registered
there in the same operation, on a real event database with the HTTP boundary
mocked.
"""

from datetime import datetime, timedelta
from typing import Any
from unittest import TestCase
from unittest.mock import MagicMock

import pytest

from data.event import Event
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer, StoredTournamentPlayer
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_data import SCEEventPluginData, SCEPlayerPluginData, SCETokens
from plugins.sce.sce_session import SCESession
from plugins.sce.utils import SCEUtils
from tests.test_config import TestUtils

EVENT_UNIQ_ID = 'test-sce-upload-local-tournament'
SCE_TOURNAMENT_ID = 'SCE-NEW-T'


class UploadHarness:
    """Answers the tournament creation, then each registration op."""

    def __init__(self, conflicts: set[str] | None = None) -> None:
        self.conflicts = conflicts or set()
        self.batches: list[list[dict[str, Any]]] = []

    def answer(self, request_function: Any, skip_validation: bool = False) -> Any:
        response = MagicMock()
        response.status_code = 200
        if request_function.func.__name__ == '_create_tournament_request':
            response.json.return_value = {'data': {'id': SCE_TOURNAMENT_ID}}
            return response
        ops = request_function.keywords['ops']
        self.batches.append(ops)
        results = []
        for index, op in enumerate(ops):
            if op['data']['last_name'] in self.conflicts:
                results.append(
                    {
                        'index': index,
                        'status': 'error',
                        'error': {
                            'code': 'conflict',
                            'message': 'duplicate',
                            'existing_registration_id': 'SCE-EXISTING',
                        },
                    }
                )
            else:
                results.append(
                    {
                        'index': index,
                        'status': 'ok',
                        'registration_id': f'SCE-{op["data"]["last_name"]}',
                    }
                )
        response.status_code = 207 if self.conflicts else 200
        response.json.return_value = {'results': results}
        return response

    @property
    def ops(self) -> list[dict[str, Any]]:
        return [op for batch in self.batches for op in batch]


@pytest.mark.unit
class TestUploadLocalTournament(TestCase):
    def setUp(self) -> None:
        super().setUp()
        TestUtils.create_event(EVENT_UNIQ_ID)
        stored_tournament = TestUtils.create_tournament(EVENT_UNIQ_ID, 'Local')
        assert stored_tournament.id is not None
        self.tournament_id = stored_tournament.id
        plugin_data = SCEEventPluginData(
            id='SCE-EVT',
            tokens=SCETokens(
                access_token='ACCESS',
                refresh_token='REFRESH',
                expires_at=datetime.now() + timedelta(hours=1),
            ),
        )
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            stored_event = database.load_stored_event()
            stored_event.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
            stored_event.enabled_plugins = [*stored_event.enabled_plugins, PLUGIN_NAME]
            database.update_stored_event(stored_event)

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_UNIQ_ID)
        super().tearDown()

    def add_player(self, last_name: str, plugin_data: dict | None = None) -> int:
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            player_id = database.add_stored_player(
                StoredPlayer(
                    id=None,
                    last_name=last_name,
                    first_name='Player',
                    year_of_birth=1990,
                    federation='FRA',
                    plugin_data={PLUGIN_NAME: plugin_data or {}},
                )
            )
            database.add_stored_tournament_player(
                StoredTournamentPlayer(
                    player_id=player_id, tournament_id=self.tournament_id
                )
            )
        return player_id

    def upload(self, harness: UploadHarness) -> int:
        self.event = EventLoader().load_event(EVENT_UNIQ_ID)
        session = SCESession(self.event)
        session._run_with_token_validation = MagicMock(  # type: ignore[method-assign]
            side_effect=harness.answer
        )
        return session.create_sce_tournament(
            self.event.tournaments_by_id[self.tournament_id]
        )

    def reload(self) -> Event:
        self.event = EventLoader().load_event(EVENT_UNIQ_ID)
        return self.event

    def player_plugin_data(self, player_id: int) -> SCEPlayerPluginData:
        player = self.reload().players_by_id[player_id]
        return SCEUtils.get_player_plugin_data(player)

    def test_players_are_registered_with_the_tournament(self) -> None:
        alpha = self.add_player('ALPHA')
        bravo = self.add_player('BRAVO')
        harness = UploadHarness()

        duplicate_count = self.upload(harness)

        assert duplicate_count == 0
        assert len(harness.batches) == 1
        assert sorted(op['data']['last_name'] for op in harness.ops) == [
            'ALPHA',
            'BRAVO',
        ]
        assert all(op['op'] == 'create' for op in harness.ops)
        assert all(op['tournament_id'] == SCE_TOURNAMENT_ID for op in harness.ops)
        assert self.player_plugin_data(alpha).id == 'SCE-ALPHA'
        assert self.player_plugin_data(bravo).id == 'SCE-BRAVO'

    def test_tournament_is_linked(self) -> None:
        self.add_player('ALPHA')

        self.upload(UploadHarness())

        tournament = self.reload().tournaments_by_id[self.tournament_id]
        assert SCEUtils.get_tournament_plugin_data(tournament).id == SCE_TOURNAMENT_ID

    def test_duplicates_are_counted(self) -> None:
        self.add_player('ALPHA')
        bravo = self.add_player('BRAVO')

        duplicate_count = self.upload(UploadHarness(conflicts={'BRAVO'}))

        assert duplicate_count == 1
        plugin_data = self.player_plugin_data(bravo)
        assert plugin_data.id is None
        assert plugin_data.duplicated_registration_id == 'SCE-EXISTING'

    def test_empty_tournament_sends_no_batch(self) -> None:
        harness = UploadHarness()

        self.upload(harness)

        assert harness.batches == []

    def test_players_of_an_earlier_connection_are_registered_anew(self) -> None:
        linked = self.add_player('ALPHA', {'id': 'SCE-OLD-A', 'last_sync_data': None})
        removed = self.add_player('BRAVO', {'deleted_id': 'SCE-OLD-B'})
        harness = UploadHarness()

        self.upload(harness)

        assert sorted(op['data']['last_name'] for op in harness.ops) == [
            'ALPHA',
            'BRAVO',
        ]
        assert self.player_plugin_data(linked).id == 'SCE-ALPHA'
        removed_data = self.player_plugin_data(removed)
        assert removed_data.id == 'SCE-BRAVO'
        assert removed_data.deleted_id is None
        assert linked in self.reload().players_by_id

    def test_players_of_an_earlier_connection_are_not_deleted(self) -> None:
        self.add_player('ALPHA', {'id': 'SCE-OLD-A'})

        self.upload(UploadHarness())

        event = self.reload()
        assert [player.last_name for player in event.players] == ['ALPHA']
        assert SCEUtils.get_event_plugin_data(event).deleted_player_ids == []
