"""`SCESession.sync_event` when several computers share a Sharly-Chess.com event.

Each computer only holds some of the tournaments, may be the only one to hold
the pairings, and sees registrations removed or moved by the others. These
tests drive `sync_event` on a real event database under `tests/tmp/`, with the
HTTP boundary mocked: the event data SC.com returns is canned, and every batch
op sent is captured and answered with success.
"""

import json
from datetime import datetime, timedelta
from typing import Any
from unittest import TestCase
from unittest.mock import MagicMock

import pytest

from data.event import Event
from data.loader import EventLoader
from data.player import TournamentPlayer
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPairing,
    StoredPlayer,
    StoredTournamentPlayer,
)
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_data import (
    SCEEventPluginData,
    SCEPlayerPluginData,
    SCEPlayerSyncData,
    SCETokens,
    SCETournamentPluginData,
)
from plugins.sce.sce_session import SCESession
from plugins.sce.sce_managers import SCESyncStatusManager
from plugins.sce.sce_sync_status import (
    OperationFailuresSCESyncStatus,
    PlayerDuplicatesSCESyncStatus,
    SuccessSCESyncStatus,
    TournamentConflictsSCESyncStatus,
)
from plugins.sce.utils import SCEUtils
from tests.test_config import TestUtils
from utils.enum import PlayerRatingType, Result

EVENT_UNIQ_ID = 'test-sce-multi-computer'
SCE_EVENT_ID = 'SCE-EVT'
LOCAL_SCE_TOURNAMENT_ID = 'SCE-T1'
OTHER_LOCAL_SCE_TOURNAMENT_ID = 'SCE-T2'
REMOTE_SCE_TOURNAMENT_ID = 'SCE-T3'
ROUNDS = 7
# The rating a player without one gets, as SC.com holds it once synced.
ESTIMATED_RATING = 1399


def registration(
    sce_player_id: str,
    last_name: str = 'LOCAL',
    first_name: str = 'Player',
    checked_in: bool = False,
    club: str | None = None,
) -> dict[str, Any]:
    """One registration as SC.com hands it over."""
    return {
        'id': sce_player_id,
        'last_name': last_name,
        'first_name': first_name,
        'year_of_birth': 1990,
        'fide_id': None,
        'national_id': None,
        'federation': 'FRA',
        'title': None,
        'club': club,
        'rating': ESTIMATED_RATING,
        'rating_type': 'E',
        'phone_number': None,
        'comment': None,
        'gender': None,
        'checked_in': checked_in,
        'user_email': None,
        'ffe_licence_type': None,
        'ffe_league': None,
        'fra_school': None,
    }


def event_data(registrations_by_tournament: dict[str, list[dict]]) -> dict:
    """The SC.com event, with the registrations of each of its tournaments."""
    return {
        'id': SCE_EVENT_ID,
        'tournaments': [
            {
                'id': sce_tournament_id,
                'name': sce_tournament_id,
                'check_in_open': False,
                'registrations': registrations,
            }
            for sce_tournament_id, registrations in registrations_by_tournament.items()
        ],
    }


class SyncHarness:
    """Runs `sync_event` against canned SC.com data and records the batch ops."""

    def __init__(self) -> None:
        self.ops: list[dict[str, Any]] = []
        self.tournament_sync_result = True
        self.created_registration_ids: list[str] = []
        # Registration ids (or last names, for creations) whose op fails,
        # with the error code SC.com answers.
        self.errors: dict[str, str] = {}

    def run(self, data: dict) -> Any:
        event = EventLoader().load_event(EVENT_UNIQ_ID)
        session = SCESession(event)
        session._sync_tournament = MagicMock(  # type: ignore[method-assign]
            return_value=self.tournament_sync_result
        )
        session._get_event_data = MagicMock(return_value=data)  # type: ignore[method-assign]
        session._run_with_token_validation = MagicMock(  # type: ignore[method-assign]
            side_effect=self._answer
        )
        return session.sync_event()

    def _answer(self, request_function: Any, skip_validation: bool = False) -> Any:
        ops = request_function.keywords['ops']
        self.ops.extend(ops)
        results = []
        for index, op in enumerate(ops):
            key = op.get('registration_id') or op['data'].get('last_name')
            if key in self.errors:
                results.append(
                    {
                        'index': index,
                        'status': 'error',
                        'error': {'code': self.errors[key], 'message': 'refused'},
                    }
                )
                continue
            result: dict[str, Any] = {'index': index, 'status': 'ok'}
            if op['op'] == 'create':
                registration_id = f'SCE-NEW-{len(self.created_registration_ids)}'
                self.created_registration_ids.append(registration_id)
                result['registration_id'] = registration_id
            results.append(result)
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {'results': results}
        return response

    def ops_of(self, kind: str) -> list[dict[str, Any]]:
        return [op for op in self.ops if op['op'] == kind]


class MultiComputerSyncTestCase(TestCase):
    """An event whose tournament T1 (and T2 where needed) is held locally,
    while SC.com also has T3, held by another computer."""

    def setUp(self) -> None:
        super().setUp()
        TestUtils.create_event(EVENT_UNIQ_ID)
        self.t1_id = self._create_linked_tournament('T1', LOCAL_SCE_TOURNAMENT_ID)
        self.t2_id = self._create_linked_tournament('T2', OTHER_LOCAL_SCE_TOURNAMENT_ID)
        self._install_event_plugin_data()
        self.harness = SyncHarness()

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_UNIQ_ID)
        super().tearDown()

    @staticmethod
    def _create_linked_tournament(name: str, sce_tournament_id: str) -> int:
        TestUtils.create_tournament(EVENT_UNIQ_ID, name, overrides={'rounds': ROUNDS})
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            stored_tournament = next(
                t for t in database.load_stored_tournaments() if t.name == name
            )
            stored_tournament.plugin_data[PLUGIN_NAME] = SCETournamentPluginData(
                id=sce_tournament_id
            ).to_stored_value()
            database.execute(
                'UPDATE `tournament` SET `plugin_data` = ? WHERE `id` = ?',
                (json.dumps(stored_tournament.plugin_data), stored_tournament.id),
            )
            assert stored_tournament.id is not None
            return stored_tournament.id

    @staticmethod
    def _install_event_plugin_data(deleted_player_ids: list[str] | None = None) -> None:
        plugin_data = SCEEventPluginData(
            id=SCE_EVENT_ID,
            tokens=SCETokens(
                access_token='ACCESS',
                refresh_token='REFRESH',
                expires_at=datetime.now() + timedelta(hours=1),
            ),
            deleted_player_ids=deleted_player_ids or [],
        )
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            stored_event = database.load_stored_event()
            stored_event.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
            if PLUGIN_NAME not in stored_event.enabled_plugins:
                stored_event.enabled_plugins = [
                    *stored_event.enabled_plugins,
                    PLUGIN_NAME,
                ]
            database.update_stored_event(stored_event)

    def add_player(
        self,
        sce_player_id: str | None,
        last_name: str = 'LOCAL',
        tournament_id: int | None = None,
        paired: bool = False,
        plugin_data: dict[str, Any] | None = None,
    ) -> int:
        """A local player linked to `sce_player_id`, in sync with SC.com.

        A paired player received the pairing-allocated bye of round 1.
        """
        tournament_id = tournament_id or self.t1_id
        sce_tournament_id = (
            LOCAL_SCE_TOURNAMENT_ID
            if tournament_id == self.t1_id
            else OTHER_LOCAL_SCE_TOURNAMENT_ID
        )
        if plugin_data is None:
            plugin_data = SCEPlayerPluginData(
                id=sce_player_id,
                last_sync_data=self.sync_data(sce_tournament_id, last_name),
            ).to_stored_value()
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            player_id = database.add_stored_player(
                StoredPlayer(
                    id=None,
                    last_name=last_name,
                    first_name='Player',
                    year_of_birth=1990,
                    federation='FRA',
                    plugin_data={PLUGIN_NAME: plugin_data},
                )
            )
            database.add_stored_tournament_player(
                StoredTournamentPlayer(player_id=player_id, tournament_id=tournament_id)
            )
            if paired:
                database.add_stored_pairing(
                    StoredPairing(
                        tournament_id=tournament_id,
                        player_id=player_id,
                        round_=1,
                        result=Result.PAIRING_ALLOCATED_BYE.value,
                        board_id=None,
                    )
                )
        return player_id

    @staticmethod
    def sync_data(
        sce_tournament_id: str, last_name: str = 'LOCAL'
    ) -> SCEPlayerSyncData:
        return SCEPlayerSyncData(
            tournament_id=sce_tournament_id,
            last_name=last_name,
            first_name='Player',
            year_of_birth=1990,
            federation='FRA',
            rating=ESTIMATED_RATING,
            rating_type=PlayerRatingType.ESTIMATED,
        )

    def load_event(self) -> Event:
        # Players only hold a weak reference to their event.
        self.event = EventLoader().load_event(EVENT_UNIQ_ID)
        return self.event

    def player(self, player_id: int) -> TournamentPlayer:
        return self.load_event().players_by_id[player_id].single_tournament_player

    def player_exists(self, player_id: int) -> bool:
        return player_id in self.load_event().players_by_id

    def player_plugin_data(self, player_id: int) -> SCEPlayerPluginData:
        return SCEUtils.get_player_plugin_data(self.player(player_id))

    def deleted_player_ids(self) -> list[str]:
        return SCEUtils.get_event_plugin_data(self.load_event()).deleted_player_ids

    def local_last_names(self) -> set[str]:
        return {player.last_name for player in self.load_event().players}


@pytest.mark.unit
class TestInSyncBaseline(MultiComputerSyncTestCase):
    def test_players_in_sync_send_nothing(self) -> None:
        self.add_player('SCE-A', 'ALPHA')
        self.add_player('SCE-B', 'BRAVO', paired=True)

        status = self.harness.run(
            event_data(
                {
                    LOCAL_SCE_TOURNAMENT_ID: [
                        registration('SCE-A', 'ALPHA'),
                        registration('SCE-B', 'BRAVO'),
                    ],
                    OTHER_LOCAL_SCE_TOURNAMENT_ID: [],
                }
            )
        )

        assert self.harness.ops == []
        assert isinstance(status, SuccessSCESyncStatus)


@pytest.mark.unit
class TestRegistrationRemovedOnSCE(MultiComputerSyncTestCase):
    """The registration of a local player is gone from SC.com."""

    def removed(self) -> dict:
        return event_data(
            {LOCAL_SCE_TOURNAMENT_ID: [], OTHER_LOCAL_SCE_TOURNAMENT_ID: []}
        )

    def test_paired_player_is_kept_without_byes_and_awaits_the_arbiter(self) -> None:
        player_id = self.add_player('SCE-A', paired=True)

        self.harness.run(self.removed())

        player = self.player(player_id)
        plugin_data = SCEUtils.get_player_plugin_data(player)
        assert plugin_data.id is None
        assert plugin_data.deleted_id == 'SCE-A'
        assert plugin_data.removal_pending is True
        for round_ in range(2, ROUNDS + 1):
            assert player.pairings[round_].unpaired, f'round {round_} got a bye'
        assert player.pairings[1].result == Result.PAIRING_ALLOCATED_BYE

    def test_paired_player_removal_sends_nothing_to_sce(self) -> None:
        self.add_player('SCE-A', paired=True)

        self.harness.run(self.removed())

        assert self.harness.ops == []
        assert self.deleted_player_ids() == []

    def test_unpaired_player_is_deleted_locally(self) -> None:
        player_id = self.add_player('SCE-A')

        self.harness.run(self.removed())

        assert not self.player_exists(player_id)

    def test_unpaired_player_deletion_is_not_queued_for_sce(self) -> None:
        self.add_player('SCE-A')

        self.harness.run(self.removed())

        assert self.deleted_player_ids() == []
        assert self.harness.ops_of('delete') == []

    def test_registration_back_after_local_deletion_is_imported_not_deleted(
        self,
    ) -> None:
        self.add_player('SCE-A', 'ALPHA')
        self.harness.run(self.removed())

        self.harness.run(
            event_data(
                {
                    LOCAL_SCE_TOURNAMENT_ID: [registration('SCE-A', 'ALPHA')],
                    OTHER_LOCAL_SCE_TOURNAMENT_ID: [],
                }
            )
        )

        assert self.harness.ops_of('delete') == []
        players = [p for p in self.load_event().players if p.last_name == 'ALPHA']
        assert len(players) == 1
        assert SCEUtils.get_player_plugin_data(players[0]).id == 'SCE-A'

    def test_paired_player_is_relinked_when_registration_comes_back(self) -> None:
        player_id = self.add_player('SCE-A', 'ALPHA', paired=True)
        self.harness.run(self.removed())

        self.harness.run(
            event_data(
                {
                    LOCAL_SCE_TOURNAMENT_ID: [registration('SCE-A', 'ALPHA')],
                    OTHER_LOCAL_SCE_TOURNAMENT_ID: [],
                }
            )
        )

        plugin_data = self.player_plugin_data(player_id)
        assert plugin_data.id == 'SCE-A'
        assert plugin_data.deleted_id is None
        assert plugin_data.removal_pending is False
        assert [p.last_name for p in self.load_event().players] == ['ALPHA']
        assert self.harness.ops_of('create') == []

    def test_only_removed_players_are_affected(self) -> None:
        kept_id = self.add_player('SCE-A', 'ALPHA')
        removed_id = self.add_player('SCE-B', 'BRAVO')

        self.harness.run(
            event_data(
                {
                    LOCAL_SCE_TOURNAMENT_ID: [registration('SCE-A', 'ALPHA')],
                    OTHER_LOCAL_SCE_TOURNAMENT_ID: [],
                }
            )
        )

        assert self.player_exists(kept_id)
        assert not self.player_exists(removed_id)


@pytest.mark.unit
class TestRegistrationMovedToTournamentNotHeldHere(MultiComputerSyncTestCase):
    """Another computer moved the registration to T3, which is not held here."""

    def moved(self, last_name: str = 'LOCAL') -> dict:
        return event_data(
            {
                LOCAL_SCE_TOURNAMENT_ID: [],
                OTHER_LOCAL_SCE_TOURNAMENT_ID: [],
                REMOTE_SCE_TOURNAMENT_ID: [registration('SCE-A', last_name)],
            }
        )

    def test_unpaired_player_is_removed_locally(self) -> None:
        player_id = self.add_player('SCE-A')

        self.harness.run(self.moved())

        assert not self.player_exists(player_id)

    def test_unpaired_player_removal_is_not_sent_to_sce(self) -> None:
        self.add_player('SCE-A')

        self.harness.run(self.moved())

        assert self.harness.ops == []
        assert self.deleted_player_ids() == []

    def test_paired_player_is_kept_and_forced_back(self) -> None:
        player_id = self.add_player('SCE-A', paired=True)

        self.harness.run(self.moved())

        plugin_data = self.player_plugin_data(player_id)
        assert plugin_data.id == 'SCE-A'
        assert plugin_data.removal_pending is False
        updates = self.harness.ops_of('update')
        assert len(updates) == 1
        assert updates[0]['registration_id'] == 'SCE-A'
        assert updates[0]['tournament_id'] == LOCAL_SCE_TOURNAMENT_ID
        assert self.harness.ops_of('delete') == []

    def test_paired_player_keeps_its_pairings_and_tournament(self) -> None:
        player_id = self.add_player('SCE-A', paired=True)

        self.harness.run(self.moved())

        player = self.player(player_id)
        assert player.tournament.id == self.t1_id
        assert player.pairings[1].result == Result.PAIRING_ALLOCATED_BYE
        for round_ in range(2, ROUNDS + 1):
            assert player.pairings[round_].unpaired

    def test_registrations_of_other_tournaments_are_not_imported(self) -> None:
        self.harness.run(
            event_data(
                {
                    LOCAL_SCE_TOURNAMENT_ID: [],
                    OTHER_LOCAL_SCE_TOURNAMENT_ID: [],
                    REMOTE_SCE_TOURNAMENT_ID: [registration('SCE-X', 'XRAY')],
                }
            )
        )

        assert self.local_last_names() == set()
        assert self.harness.ops == []

    def test_move_between_local_tournaments_moves_the_player(self) -> None:
        player_id = self.add_player('SCE-A')

        self.harness.run(
            event_data(
                {
                    LOCAL_SCE_TOURNAMENT_ID: [],
                    OTHER_LOCAL_SCE_TOURNAMENT_ID: [registration('SCE-A')],
                }
            )
        )

        player = self.player(player_id)
        assert player.tournament.id == self.t2_id
        assert self.player_plugin_data(player_id).id == 'SCE-A'
        assert self.harness.ops == []

    def test_queued_deletion_of_a_registration_moved_away_is_dropped(self) -> None:
        self._install_event_plugin_data(deleted_player_ids=['SCE-GONE'])

        self.harness.run(
            event_data(
                {
                    LOCAL_SCE_TOURNAMENT_ID: [],
                    OTHER_LOCAL_SCE_TOURNAMENT_ID: [],
                    REMOTE_SCE_TOURNAMENT_ID: [registration('SCE-GONE')],
                }
            )
        )

        assert self.harness.ops_of('delete') == []
        assert self.deleted_player_ids() == []

    def test_queued_deletion_in_a_local_tournament_is_still_sent(self) -> None:
        self._install_event_plugin_data(deleted_player_ids=['SCE-GONE'])

        self.harness.run(
            event_data(
                {
                    LOCAL_SCE_TOURNAMENT_ID: [registration('SCE-GONE')],
                    OTHER_LOCAL_SCE_TOURNAMENT_ID: [],
                }
            )
        )

        deletes = self.harness.ops_of('delete')
        assert [op['registration_id'] for op in deletes] == ['SCE-GONE']
        assert self.deleted_player_ids() == []
        assert self.local_last_names() == set()


@pytest.mark.unit
class TestUserDeletion(MultiComputerSyncTestCase):
    def test_user_deletion_is_queued_and_sent(self) -> None:
        player_id = self.add_player('SCE-A')
        event = self.load_event()
        event.delete_player(event.players_by_id[player_id])
        assert self.deleted_player_ids() == ['SCE-A']

        self.harness.run(
            event_data(
                {
                    LOCAL_SCE_TOURNAMENT_ID: [registration('SCE-A')],
                    OTHER_LOCAL_SCE_TOURNAMENT_ID: [],
                }
            )
        )

        deletes = self.harness.ops_of('delete')
        assert [op['registration_id'] for op in deletes] == ['SCE-A']
        assert self.deleted_player_ids() == []


@pytest.mark.unit
class TestTournamentConflicts(MultiComputerSyncTestCase):
    def test_players_sync_despite_tournament_conflicts(self) -> None:
        self.harness.tournament_sync_result = False

        status = self.harness.run(
            event_data(
                {
                    LOCAL_SCE_TOURNAMENT_ID: [registration('SCE-N', 'NEW')],
                    OTHER_LOCAL_SCE_TOURNAMENT_ID: [],
                }
            )
        )

        assert self.local_last_names() == {'NEW'}
        assert isinstance(status, TournamentConflictsSCESyncStatus)

    def test_local_changes_are_pushed_despite_tournament_conflicts(self) -> None:
        self.harness.tournament_sync_result = False
        self.add_player('SCE-A', 'RENAMED')
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            database.execute(
                'UPDATE `player` SET `plugin_data` = ? WHERE `last_name` = ?',
                (
                    json.dumps(
                        {
                            PLUGIN_NAME: SCEPlayerPluginData(
                                id='SCE-A',
                                last_sync_data=self.sync_data(
                                    LOCAL_SCE_TOURNAMENT_ID, 'ORIGINAL'
                                ),
                            ).to_stored_value()
                        }
                    ),
                    'RENAMED',
                ),
            )

        self.harness.run(
            event_data(
                {
                    LOCAL_SCE_TOURNAMENT_ID: [registration('SCE-A', 'ORIGINAL')],
                    OTHER_LOCAL_SCE_TOURNAMENT_ID: [],
                }
            )
        )

        updates = self.harness.ops_of('update')
        assert len(updates) == 1
        assert updates[0]['data'] == {'last_name': 'RENAMED'}

    def test_tournament_conflict_status_records_the_sync(self) -> None:
        assert TournamentConflictsSCESyncStatus().update_last_sync_at is True


@pytest.mark.unit
class TestRemovedPlayerDecisions(MultiComputerSyncTestCase):
    """The arbiter's decision on a player removed on SC.com after playing."""

    def remove_paired_player(self) -> int:
        player_id = self.add_player('SCE-A', 'ALPHA', paired=True)
        self.harness.run(
            event_data({LOCAL_SCE_TOURNAMENT_ID: [], OTHER_LOCAL_SCE_TOURNAMENT_ID: []})
        )
        assert self.player_plugin_data(player_id).removal_pending
        return player_id

    def test_removed_player_is_listed_as_pending(self) -> None:
        player_id = self.remove_paired_player()
        self.add_player('SCE-B', 'BRAVO')

        pending = SCEUtils.get_players_removal_pending(self.load_event())

        assert [player.id for player in pending] == [player_id]

    def test_withdraw_gives_byes_in_every_unpaired_round(self) -> None:
        player_id = self.remove_paired_player()

        SCESession.withdraw_removed_player(self.player(player_id))

        player = self.player(player_id)
        assert player.pairings[1].result == Result.PAIRING_ALLOCATED_BYE
        for round_ in range(2, ROUNDS + 1):
            assert player.pairings[round_].result == Result.ZERO_POINT_BYE

    def test_withdraw_keeps_byes_already_requested(self) -> None:
        player_id = self.remove_paired_player()
        player = self.player(player_id)
        player.tournament.set_player_byes(
            player, {4: Result.HALF_POINT_BYE, 5: Result.FULL_POINT_BYE}
        )

        SCESession.withdraw_removed_player(self.player(player_id))

        player = self.player(player_id)
        assert player.pairings[4].result == Result.HALF_POINT_BYE
        assert player.pairings[5].result == Result.FULL_POINT_BYE
        for round_ in (2, 3, 6, 7):
            assert player.pairings[round_].result == Result.ZERO_POINT_BYE

    def test_withdraw_closes_the_decision(self) -> None:
        player_id = self.remove_paired_player()

        SCESession.withdraw_removed_player(self.player(player_id))

        plugin_data = self.player_plugin_data(player_id)
        assert plugin_data.removal_pending is False
        assert plugin_data.deleted_id == 'SCE-A'
        assert SCEUtils.get_players_removal_pending(self.load_event()) == []

    def test_withdrawn_player_is_not_registered_again(self) -> None:
        player_id = self.remove_paired_player()
        SCESession.withdraw_removed_player(self.player(player_id))

        self.harness.run(
            event_data({LOCAL_SCE_TOURNAMENT_ID: [], OTHER_LOCAL_SCE_TOURNAMENT_ID: []})
        )

        assert self.harness.ops == []

    def test_keep_registers_the_player_again_at_next_sync(self) -> None:
        player_id = self.remove_paired_player()

        SCESession.register_removed_player_again(self.player(player_id))
        self.harness.run(
            event_data({LOCAL_SCE_TOURNAMENT_ID: [], OTHER_LOCAL_SCE_TOURNAMENT_ID: []})
        )

        creates = self.harness.ops_of('create')
        assert len(creates) == 1
        assert creates[0]['tournament_id'] == LOCAL_SCE_TOURNAMENT_ID
        assert creates[0]['data']['last_name'] == 'ALPHA'
        plugin_data = self.player_plugin_data(player_id)
        assert plugin_data.id == self.harness.created_registration_ids[0]
        assert plugin_data.deleted_id is None
        assert plugin_data.removal_pending is False

    def test_keep_leaves_the_pairings_untouched(self) -> None:
        player_id = self.remove_paired_player()

        SCESession.register_removed_player_again(self.player(player_id))

        player = self.player(player_id)
        assert player.pairings[1].result == Result.PAIRING_ALLOCATED_BYE
        for round_ in range(2, ROUNDS + 1):
            assert player.pairings[round_].unpaired

    def test_decisions_ignore_players_not_pending(self) -> None:
        player_id = self.add_player('SCE-A', paired=True)

        SCESession.withdraw_removed_player(self.player(player_id))
        SCESession.register_removed_player_again(self.player(player_id))

        player = self.player(player_id)
        assert SCEUtils.get_player_plugin_data(player).id == 'SCE-A'
        for round_ in range(2, ROUNDS + 1):
            assert player.pairings[round_].unpaired

    def test_soft_deletion_from_earlier_versions_is_not_pending(self) -> None:
        self.add_player(
            None,
            paired=True,
            plugin_data={'id': None, 'deleted_id': 'SCE-OLD'},
        )

        assert SCEUtils.get_players_removal_pending(self.load_event()) == []


@pytest.mark.unit
class TestOperationFailures(MultiComputerSyncTestCase):
    """A change SC.com refuses is reported, and sent again at the next sync."""

    def renamed_locally(self) -> None:
        self.add_player('SCE-A', 'RENAMED')
        with EventDatabase(EVENT_UNIQ_ID, write=True) as database:
            database.execute(
                'UPDATE `player` SET `plugin_data` = ? WHERE `last_name` = ?',
                (
                    json.dumps(
                        {
                            PLUGIN_NAME: SCEPlayerPluginData(
                                id='SCE-A',
                                last_sync_data=self.sync_data(
                                    LOCAL_SCE_TOURNAMENT_ID, 'ORIGINAL'
                                ),
                            ).to_stored_value()
                        }
                    ),
                    'RENAMED',
                ),
            )

    @staticmethod
    def original() -> dict:
        return event_data(
            {
                LOCAL_SCE_TOURNAMENT_ID: [registration('SCE-A', 'ORIGINAL')],
                OTHER_LOCAL_SCE_TOURNAMENT_ID: [],
            }
        )

    def test_status_is_registered(self) -> None:
        status = SCESyncStatusManager().get_object(
            OperationFailuresSCESyncStatus.static_id()
        )

        assert isinstance(status, OperationFailuresSCESyncStatus)
        assert status.notify_error_status
        assert not status.update_last_sync_at

    def test_refused_update_is_reported(self) -> None:
        self.renamed_locally()
        self.harness.errors['SCE-A'] = 'internal_error'

        status = self.harness.run(self.original())

        assert isinstance(status, OperationFailuresSCESyncStatus)

    def test_refused_update_is_sent_again(self) -> None:
        self.renamed_locally()
        self.harness.errors['SCE-A'] = 'internal_error'
        self.harness.run(self.original())
        self.harness.errors.clear()
        self.harness.ops.clear()

        status = self.harness.run(self.original())

        updates = self.harness.ops_of('update')
        assert [op['data'] for op in updates] == [{'last_name': 'RENAMED'}]
        assert isinstance(status, SuccessSCESyncStatus)

    def test_refused_creation_is_reported_and_sent_again(self) -> None:
        player_id = self.add_player(None, 'NEWCOMER', plugin_data={})
        self.harness.errors['NEWCOMER'] = 'internal_error'
        empty = event_data(
            {LOCAL_SCE_TOURNAMENT_ID: [], OTHER_LOCAL_SCE_TOURNAMENT_ID: []}
        )

        status = self.harness.run(empty)

        assert isinstance(status, OperationFailuresSCESyncStatus)
        assert self.player_plugin_data(player_id).id is None
        self.harness.errors.clear()
        assert isinstance(self.harness.run(empty), SuccessSCESyncStatus)
        assert self.player_plugin_data(player_id).id is not None

    def test_duplicate_is_not_a_failure(self) -> None:
        self.add_player(None, 'NEWCOMER', plugin_data={})
        self.harness.errors['NEWCOMER'] = 'conflict'

        status = self.harness.run(
            event_data({LOCAL_SCE_TOURNAMENT_ID: [], OTHER_LOCAL_SCE_TOURNAMENT_ID: []})
        )

        assert isinstance(status, PlayerDuplicatesSCESyncStatus)

    def test_refused_deletion_is_reported_and_kept_queued(self) -> None:
        self._install_event_plugin_data(deleted_player_ids=['SCE-GONE'])
        self.harness.errors['SCE-GONE'] = 'internal_error'

        status = self.harness.run(
            event_data(
                {
                    LOCAL_SCE_TOURNAMENT_ID: [registration('SCE-GONE')],
                    OTHER_LOCAL_SCE_TOURNAMENT_ID: [],
                }
            )
        )

        assert isinstance(status, OperationFailuresSCESyncStatus)
        assert self.deleted_player_ids() == ['SCE-GONE']

    def test_deletion_already_done_is_not_a_failure(self) -> None:
        self._install_event_plugin_data(deleted_player_ids=['SCE-GONE'])
        self.harness.errors['SCE-GONE'] = 'not_found'

        status = self.harness.run(
            event_data(
                {
                    LOCAL_SCE_TOURNAMENT_ID: [registration('SCE-GONE')],
                    OTHER_LOCAL_SCE_TOURNAMENT_ID: [],
                }
            )
        )

        assert isinstance(status, SuccessSCESyncStatus)

    def test_refused_tournament_move_is_reported(self) -> None:
        self.add_player('SCE-A', paired=True)
        self.harness.errors['SCE-A'] = 'internal_error'

        status = self.harness.run(
            event_data(
                {
                    LOCAL_SCE_TOURNAMENT_ID: [],
                    OTHER_LOCAL_SCE_TOURNAMENT_ID: [],
                    REMOTE_SCE_TOURNAMENT_ID: [registration('SCE-A')],
                }
            )
        )

        assert isinstance(status, OperationFailuresSCESyncStatus)

    def test_failures_come_before_tournament_conflicts(self) -> None:
        self.renamed_locally()
        self.harness.errors['SCE-A'] = 'internal_error'
        self.harness.tournament_sync_result = False

        status = self.harness.run(self.original())

        assert isinstance(status, OperationFailuresSCESyncStatus)
