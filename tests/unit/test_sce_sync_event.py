"""`SCESession.sync_event`, orchestrated end to end.

Real Event/Tournament/Player in a SQLite DB under `tests/tmp/`. SC.com
HTTP boundary is mocked at the `requests.post` / `_get_event_data` level
so we exercise the full sync_event orchestration: tournament-data loop,
remote-only delete step, per-player planning, batch flush, and the
event-level `deleted_player_ids` retry filter.
"""

import json
from datetime import datetime, timedelta
from unittest import TestCase
from unittest.mock import MagicMock

import pytest

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTournamentPlayer,
)
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_data import (
    SCEEventPluginData,
    SCEPlayerPluginData,
    SCETokens,
    SCETournamentPluginData,
)
from plugins.sce.sce_session import SCESession
from plugins.sce.sce_sync_status import SuccessSCESyncStatus
from plugins.sce.utils import SCEUtils

from tests.test_config import TestUtils


SCE_EVENT_ID = 'SCE-EVT'
SCE_TOURNAMENT_ID = 'SCE-T1'
EVENT_UNIQ_ID = 'test-sce-sync-event'


def _install_event_plugin_data(
    uniq_id: str,
    deleted_player_ids: list[str] | None = None,
) -> None:
    """Stamp SCEEventPluginData (with tokens + id) onto the StoredEvent."""
    epd = SCEEventPluginData(
        id=SCE_EVENT_ID,
        slug='test-event',
        organiser_slug='test-org',
        tokens=SCETokens(
            access_token='TEST-ACCESS',
            refresh_token='TEST-REFRESH',
            expires_at=datetime.now() + timedelta(hours=1),
        ),
        deleted_player_ids=deleted_player_ids or [],
    )
    with EventDatabase(uniq_id, write=True) as db:
        stored = db.load_stored_event()
        stored.plugin_data[PLUGIN_NAME] = epd.to_stored_value()
        db.update_stored_event(stored)


def _install_tournament_plugin_data(uniq_id: str, tournament_name: str) -> int:
    """Stamp SCETournamentPluginData onto the tournament and return its id."""
    tpd = SCETournamentPluginData(id=SCE_TOURNAMENT_ID)
    with EventDatabase(uniq_id, write=True) as db:
        stored_tournaments = db.load_stored_tournaments()
        stored_t = next(t for t in stored_tournaments if t.name == tournament_name)
        stored_t.plugin_data[PLUGIN_NAME] = tpd.to_stored_value()
        # Re-issue the update via raw execute since we just modify plugin_data.
        db.execute(
            'UPDATE `tournament` SET `plugin_data` = ? WHERE `id` = ?',
            (json.dumps(stored_t.plugin_data), stored_t.id),
        )
        assert stored_t.id is not None
        return stored_t.id


def _add_local_player_with_sce_id(
    uniq_id: str,
    tournament_id: int,
    sce_player_id: str,
    last_name: str = 'Local',
    first_name: str = 'Player',
) -> int:
    """Insert a StoredPlayer + StoredTournamentPlayer carrying an SCE
    plugin_data.id so the player is treated as synced from SC.com's side."""
    ppd = SCEPlayerPluginData(id=sce_player_id)
    with EventDatabase(uniq_id, write=True) as db:
        stored_player = StoredPlayer(
            id=None,
            last_name=last_name,
            first_name=first_name,
            federation='FRA',
            plugin_data={PLUGIN_NAME: ppd.to_stored_value()},
        )
        player_id = db.add_stored_player(stored_player)
        db.add_stored_tournament_player(
            StoredTournamentPlayer(player_id=player_id, tournament_id=tournament_id)
        )
        return player_id


REGISTRATION_UPDATED_AT = '2026-05-14T09:58:41.007Z'


def _canned_registration(
    sce_player_id: str,
    amount_cents: int | None = None,
    paid_cents: int | None = None,
) -> dict:
    """Shape of one registration in the SC.com `data['tournaments']`
    payload. Includes all keys the FFE + FRA-schools augment hooks read
    so they don't KeyError on canned data."""
    return {
        'amount_cents': amount_cents,
        'paid_cents': paid_cents,
        'id': sce_player_id,
        'last_name': 'Local',
        'first_name': 'Player',
        'year_of_birth': 1990,
        'fide_id': None,
        'national_id': None,
        'federation': 'FRA',
        'title': None,
        'club': None,
        'rating': None,
        'rating_type': None,
        'phone_number': None,
        'comment': None,
        'gender': None,
        'checked_in': False,
        'updated_at': REGISTRATION_UPDATED_AT,
        # FFE plugin
        'ffe_licence_type': None,
        'ffe_league': None,
        # FRA-schools plugin
        'fra_school': None,
    }


def _canned_event_data(sce_player_id: str | None = None) -> dict:
    """Mimic the shape returned by `SCESession._get_event_data`."""
    registrations: list[dict] = []
    if sce_player_id:
        registrations.append(_canned_registration(sce_player_id))
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
class TestSyncEventDeleteRetry(TestCase):
    """Failed batch deletes must keep their entry in
    `deleted_player_ids` so the next sync retries. Successful deletes
    (or 404 = already-gone) must clear the entry."""

    def setUp(self):
        super().setUp()
        TestUtils.create_event(EVENT_UNIQ_ID)
        TestUtils.create_tournament(EVENT_UNIQ_ID, 'T1')
        _install_tournament_plugin_data(EVENT_UNIQ_ID, 'T1')

    def tearDown(self):
        TestUtils.delete_event(EVENT_UNIQ_ID)
        super().tearDown()

    def _build_session_with_canned_batch(
        self, sce_player_id: str, batch_response: dict
    ) -> SCESession:
        """Load the event, install canned plugin_data, and wire mocks so
        sync_event sees `sce_player_id` as remote-only and to-be-deleted."""
        _install_event_plugin_data(EVENT_UNIQ_ID, deleted_player_ids=[sce_player_id])
        event = EventLoader().load_event(EVENT_UNIQ_ID)
        session = SCESession(event)

        # Skip tournament sync — focus on player flow.
        session._sync_tournament = MagicMock(return_value=True)  # type: ignore[method-assign]
        session._get_event_data = MagicMock(  # type: ignore[method-assign]
            return_value=_canned_event_data(sce_player_id=sce_player_id)
        )

        # Stub the HTTP send path: token validation just calls the request
        # function directly with our canned response.
        canned_resp = MagicMock()
        canned_resp.status_code = 207
        canned_resp.json.return_value = batch_response
        session._run_with_token_validation = MagicMock(  # type: ignore[method-assign]
            return_value=canned_resp
        )
        # PublishNewCheckin would call into web channels; stub it out.
        session.new_check_ins_tournament_sce_ids = set()
        return session

    def _reload_event_plugin_data(self) -> SCEEventPluginData:
        event = EventLoader().load_event(EVENT_UNIQ_ID)
        return SCEUtils.get_event_plugin_data(event)

    def test_failed_delete_preserves_id_in_deleted_player_ids(self):
        session = self._build_session_with_canned_batch(
            sce_player_id='SCE-DEAD',
            batch_response={
                'results': [
                    {
                        'index': 0,
                        'status': 'error',
                        'error': {'code': 'internal_error', 'message': 'boom'},
                    }
                ]
            },
        )

        session.sync_event()

        epd = self._reload_event_plugin_data()
        self.assertIn(
            'SCE-DEAD',
            epd.deleted_player_ids,
            'Failed SC.com delete must be retried on next sync',
        )

    def test_404_delete_treated_as_success_and_cleared(self):
        session = self._build_session_with_canned_batch(
            sce_player_id='SCE-GHOST',
            batch_response={
                'results': [
                    {
                        'index': 0,
                        'status': 'error',
                        'error': {'code': 'not_found', 'message': 'gone'},
                    }
                ]
            },
        )

        session.sync_event()

        epd = self._reload_event_plugin_data()
        self.assertNotIn(
            'SCE-GHOST',
            epd.deleted_player_ids,
            'Already-deleted-on-SC.com (404) should not be retried',
        )

    def test_delete_carries_the_read_updated_at(self):
        session = self._build_session_with_canned_batch(
            sce_player_id='SCE-OK',
            batch_response={'results': [{'index': 0, 'status': 'ok'}]},
        )

        session.sync_event()

        ops = session._run_with_token_validation.call_args.args[0].keywords['ops']  # type: ignore[attr-defined]
        assert ops == [
            {
                'op': 'delete',
                'registration_id': 'SCE-OK',
                'expected_updated_at': REGISTRATION_UPDATED_AT,
            }
        ]

    def test_stale_delete_is_retried_without_failing_the_sync(self):
        session = self._build_session_with_canned_batch(
            sce_player_id='SCE-STALE',
            batch_response={
                'results': [
                    {
                        'index': 0,
                        'status': 'error',
                        'error': {
                            'code': 'precondition_failed',
                            'message': 'Registration changed since expected_updated_at',
                        },
                    }
                ]
            },
        )

        status = session.sync_event()

        self.assertIsInstance(status, SuccessSCESyncStatus)
        self.assertEqual(session.stale_count, 1)
        self.assertIn('SCE-STALE', self._reload_event_plugin_data().deleted_player_ids)

    def test_successful_delete_clears_from_deleted_player_ids(self):
        session = self._build_session_with_canned_batch(
            sce_player_id='SCE-OK',
            batch_response={'results': [{'index': 0, 'status': 'ok'}]},
        )

        session.sync_event()

        epd = self._reload_event_plugin_data()
        self.assertNotIn('SCE-OK', epd.deleted_player_ids)


MOVE_EVENT_UNIQ_ID = 'test-sce-sync-event-move'


@pytest.mark.unit
class TestSyncEventLocalMove(TestCase):
    """Local-only move (player moved between local tournaments) should
    push an UPDATE op with op-level `tournament_id` = target so the
    server triggers the move."""

    def setUp(self):
        super().setUp()
        TestUtils.create_event(MOVE_EVENT_UNIQ_ID)

    def tearDown(self):
        TestUtils.delete_event(MOVE_EVENT_UNIQ_ID)
        super().tearDown()

    def test_batch_payload_carries_target_tournament_id(self):
        from plugins.sce.sce_data import SCEPlayerSyncData
        from utils.enum import PlayerGender

        # Two tournaments: SCE-T1 (source), SCE-T2 (target).
        TestUtils.create_tournament(MOVE_EVENT_UNIQ_ID, 'T1')
        TestUtils.create_tournament(MOVE_EVENT_UNIQ_ID, 'T2')

        # Tag tournaments with their SCE IDs.
        with EventDatabase(MOVE_EVENT_UNIQ_ID, write=True) as db:
            stored_ts = db.load_stored_tournaments()
            for stored_t in stored_ts:
                sce_tid = 'SCE-T1' if stored_t.name == 'T1' else 'SCE-T2'
                stored_t.plugin_data[PLUGIN_NAME] = SCETournamentPluginData(
                    id=sce_tid
                ).to_stored_value()
                db.execute(
                    'UPDATE `tournament` SET `plugin_data` = ? WHERE `id` = ?',
                    (json.dumps(stored_t.plugin_data), stored_t.id),
                )
            t2_id = next(t.id for t in stored_ts if t.name == 'T2')
            assert t2_id is not None

        _install_event_plugin_data(MOVE_EVENT_UNIQ_ID)

        # Player currently in T2 locally (already "moved"), known to SC as
        # being in T1 still. last_sync_data captures the pre-move state.
        last_sync = SCEPlayerSyncData(
            tournament_id='SCE-T1',
            last_name='LOCAL',
            first_name='Player',
            federation='FRA',
            year_of_birth=1990,
            gender=PlayerGender.NONE,
        )
        ppd = SCEPlayerPluginData(id='SCE-MOVER', last_sync_data=last_sync)
        with EventDatabase(MOVE_EVENT_UNIQ_ID, write=True) as db:
            stored_player = StoredPlayer(
                id=None,
                last_name='Local',
                first_name='Player',
                year_of_birth=1990,
                federation='FRA',
                plugin_data={PLUGIN_NAME: ppd.to_stored_value()},
            )
            player_id = db.add_stored_player(stored_player)
            db.add_stored_tournament_player(
                StoredTournamentPlayer(player_id=player_id, tournament_id=t2_id)
            )

        event = EventLoader().load_event(MOVE_EVENT_UNIQ_ID)
        session = SCESession(event)

        session._sync_tournament = MagicMock(return_value=True)  # type: ignore[method-assign]
        # SC says player is still in SCE-T1.
        sc_event_data = _canned_event_data(sce_player_id=None)
        sc_event_data['tournaments'] = [
            {
                'id': 'SCE-T1',
                'name': 'T1',
                'registrations': [_canned_registration('SCE-MOVER')],
            },
            {'id': 'SCE-T2', 'name': 'T2', 'registrations': []},
        ]
        session._get_event_data = MagicMock(return_value=sc_event_data)  # type: ignore[method-assign]

        # Capture the batch POST body without actually hitting HTTP.
        captured_bodies: list[dict] = []

        def fake_runner(fn, skip_validation=False):
            # fn is a partial wrapping _send_batch_request(ops=...)
            ops = fn.keywords['ops']
            captured_bodies.append({'ops': ops})
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                'results': [
                    {
                        'index': i,
                        'status': 'ok',
                        'registration_id': op.get('registration_id'),
                    }
                    for i, op in enumerate(ops)
                ]
            }
            return resp

        session._run_with_token_validation = MagicMock(side_effect=fake_runner)  # type: ignore[method-assign]

        session.sync_event()

        # Find the UPDATE op for our player. Op-level tournament_id must be
        # the local target (SCE-T2), not the source (SCE-T1).
        all_ops = [op for body in captured_bodies for op in body['ops']]
        update_ops = [
            op
            for op in all_ops
            if op['op'] == 'update' and op.get('registration_id') == 'SCE-MOVER'
        ]
        self.assertTrue(update_ops, 'Expected at least one UPDATE op for SCE-MOVER')
        self.assertEqual(
            update_ops[0]['tournament_id'],
            'SCE-T2',
            'op-level tournament_id must be the move target',
        )


PAYMENT_EVENT_UNIQ_ID = 'test-sce-sync-event-payment'


@pytest.mark.unit
class TestSyncEventPayment(TestCase):
    """The fees of SC.com registrations reach the stored players, and the
    payments recorded locally survive the synchronisations that do not
    change them on SC.com."""

    def setUp(self):
        super().setUp()
        TestUtils.create_event(PAYMENT_EVENT_UNIQ_ID)
        TestUtils.create_tournament(PAYMENT_EVENT_UNIQ_ID, 'T1')
        _install_tournament_plugin_data(PAYMENT_EVENT_UNIQ_ID, 'T1')
        _install_event_plugin_data(PAYMENT_EVENT_UNIQ_ID)
        self.uploaded_ops: list[dict] = []

    def tearDown(self):
        TestUtils.delete_event(PAYMENT_EVENT_UNIQ_ID)
        super().tearDown()

    @staticmethod
    def _registration(
        sce_player_id: str,
        amount_cents: int | None = None,
        paid_cents: int | None = None,
    ) -> dict:
        """A registration as SC.com returns it once the local player has
        been uploaded, so that only the fees can differ between both ends."""
        return {
            **_canned_registration(sce_player_id, amount_cents, paid_cents),
            'last_name': 'LOCAL',
            'rating': 1399,
            'rating_type': 'E',
        }

    def _sync(self, registration: dict) -> None:
        event = EventLoader().load_event(PAYMENT_EVENT_UNIQ_ID)
        session = SCESession(event)
        session._sync_tournament = MagicMock(return_value=True)  # type: ignore[method-assign]
        event_data = _canned_event_data()
        event_data['tournaments'][0]['registrations'] = [registration]
        session._get_event_data = MagicMock(return_value=event_data)  # type: ignore[method-assign]

        def fake_runner(fn, skip_validation=False):
            ops = fn.keywords['ops']
            self.uploaded_ops.extend(ops)
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                'results': [{'index': i, 'status': 'ok'} for i, _op in enumerate(ops)]
            }
            return resp

        session._run_with_token_validation = MagicMock(side_effect=fake_runner)  # type: ignore[method-assign]
        session.sync_event()

    @staticmethod
    def _stored_player(sce_player_id: str) -> StoredPlayer:
        with EventDatabase(PAYMENT_EVENT_UNIQ_ID) as db:
            return next(
                stored_player
                for stored_player in db.load_stored_players()
                if stored_player.plugin_data.get(PLUGIN_NAME, {}).get('id')
                == sce_player_id
            )

    @staticmethod
    def _set_local_payment(sce_player_id: str, owed: float, paid: float) -> None:
        stored_player = TestSyncEventPayment._stored_player(sce_player_id)
        stored_player.owed = owed
        stored_player.paid = paid
        with EventDatabase(PAYMENT_EVENT_UNIQ_ID, write=True) as db:
            db.update_stored_player(stored_player)

    def test_registration_imported_with_its_fees(self):
        self._sync(self._registration('SCE-NEW', amount_cents=2050, paid_cents=2050))

        stored_player = self._stored_player('SCE-NEW')
        self.assertEqual(stored_player.owed, 20.5)
        self.assertEqual(stored_player.paid, 20.5)

    def test_fees_of_synced_player_imported_without_upload(self):
        self._sync(self._registration('SCE-1'))

        self._sync(self._registration('SCE-1', amount_cents=2000, paid_cents=0))

        stored_player = self._stored_player('SCE-1')
        self.assertEqual((stored_player.owed, stored_player.paid), (20.0, 0.0))
        self.assertEqual(self.uploaded_ops, [])

    def test_local_payment_kept_until_fees_change_on_sce(self):
        self._sync(self._registration('SCE-DESK', amount_cents=2000, paid_cents=0))
        self._set_local_payment('SCE-DESK', owed=20.0, paid=20.0)

        self._sync(self._registration('SCE-DESK', amount_cents=2000, paid_cents=0))
        stored_player = self._stored_player('SCE-DESK')
        self.assertEqual((stored_player.owed, stored_player.paid), (20.0, 20.0))
        self.assertEqual(self.uploaded_ops, [])

        self._sync(self._registration('SCE-DESK', amount_cents=2500, paid_cents=0))
        stored_player = self._stored_player('SCE-DESK')
        self.assertEqual((stored_player.owed, stored_player.paid), (25.0, 0.0))

    def test_registration_without_price_keeps_local_fees(self):
        self._sync(self._registration('SCE-FREE'))
        self._set_local_payment('SCE-FREE', owed=10.0, paid=5.0)

        self._sync(self._registration('SCE-FREE'))

        stored_player = self._stored_player('SCE-FREE')
        self.assertEqual((stored_player.owed, stored_player.paid), (10.0, 5.0))
