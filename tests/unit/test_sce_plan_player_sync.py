"""Unit tests for `SCESession._plan_player_sync`.

These tests exercise the 3-way merge decision tree without touching the
DB or the network. Player + plugin_data are lightweight stubs; the few
SCEUtils helpers that touch the DB are monkey-patched to operate on the
in-memory `player.plugin_data` dict.

Coverage targets the four recent bugs:
  * move target tournament_id wrong (op-level vs body)
  * dict-iter mutation during planning
  * conflict not registered when both ends modify same field
  * failed deletes silently retired from `deleted_player_ids`
"""

from unittest.mock import MagicMock

import pytest

from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_batch import SCEBatchBuilder
from plugins.sce.sce_data import SCEPlayerPluginData, SCEPlayerSyncData
from plugins.sce.sce_session import SCESession, _BatchSyncCounters


# ── Helpers ──────────────────────────────────────────────────────────────────


def make_sync_data(
    tid: str = 'T1',
    last_name: str = 'Doe',
    first_name: str | None = 'John',
    yob: int | None = 1990,
    fide_id: int | None = None,
    club: str = '',
) -> SCEPlayerSyncData:
    return SCEPlayerSyncData(
        tournament_id=tid,
        last_name=last_name,
        first_name=first_name,
        year_of_birth=yob,
        fide_id=fide_id,
        club=club,
    )


def make_player(
    plugin_data: SCEPlayerPluginData | None = None,
    last_name: str = 'Doe',
    first_name: str | None = 'John',
    has_real_pairings: bool = False,
) -> MagicMock:
    pd = plugin_data if plugin_data is not None else SCEPlayerPluginData()
    p = MagicMock()
    p.plugin_data = {PLUGIN_NAME: pd}
    p.stored_player.plugin_data = {PLUGIN_NAME: pd.to_stored_value()}
    p.last_name = last_name
    p.first_name = first_name
    p.has_real_pairings = has_real_pairings
    return p


def make_session() -> SCESession:
    session = SCESession.__new__(SCESession)
    session.event = MagicMock()
    session.event.uniq_id = 'test-event'
    session.new_check_ins_tournament_sce_ids = set()
    return session


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def stub_db_writes(monkeypatch):
    """update_player_plugin_data normally writes to SQLite. Stub it to mutate
    in-memory player state only so tests can inspect outcomes."""

    def fake_update(player, plugin_data, write=True, write_stored_object=False):
        player.stored_player.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
        player.plugin_data[PLUGIN_NAME] = plugin_data

    monkeypatch.setattr(
        'plugins.sce.utils.SCEUtils.update_player_plugin_data', fake_update
    )


@pytest.fixture
def session():
    s = make_session()
    # update_local_player would call augment_stored_player + DB; stub it.
    s.update_local_player = MagicMock()  # type: ignore[method-assign]
    return s


@pytest.fixture
def builder():
    return SCEBatchBuilder()


@pytest.fixture
def counters():
    return _BatchSyncCounters()


def _patch_from_player(monkeypatch, sync_data: SCEPlayerSyncData):
    monkeypatch.setattr(
        'plugins.sce.sce_data.SCEPlayerSyncData.from_player',
        classmethod(lambda cls, player: sync_data),
    )


# ── Branch A: no sce_id (create) ────────────────────────────────────────────


@pytest.mark.unit
class TestCreateBranch:
    def test_no_sce_id_queues_create_op(self, session, builder, counters, monkeypatch):
        local = make_sync_data(tid='T1', last_name='Carlsen', fide_id=1503014)
        _patch_from_player(monkeypatch, local)
        player = make_player()

        session._plan_player_sync(player, None, builder, counters)

        assert len(builder) == 1
        op = builder.pending[0]
        assert op.op_dict['op'] == 'create'
        assert op.op_dict['tournament_id'] == 'T1'
        assert op.op_dict['data']['last_name'] == 'Carlsen'
        assert 'tournament_id' not in op.op_dict['data']

    def test_create_success_sets_id_and_last_sync_data(
        self, session, builder, counters, monkeypatch
    ):
        local = make_sync_data(tid='T1')
        _patch_from_player(monkeypatch, local)
        player = make_player()

        session._plan_player_sync(player, None, builder, counters)
        builder.pending[0].on_success(
            {'index': 0, 'status': 'ok', 'registration_id': 'SCE-REG-42'}
        )

        pd = player.plugin_data[PLUGIN_NAME]
        assert pd.id == 'SCE-REG-42'
        assert pd.last_sync_data == local
        assert pd.is_duplicated is False

    def test_create_conflict_marks_duplicated(
        self, session, builder, counters, monkeypatch
    ):
        local = make_sync_data(tid='T1')
        _patch_from_player(monkeypatch, local)
        player = make_player()

        session._plan_player_sync(player, None, builder, counters)
        builder.pending[0].on_error(
            {
                'index': 0,
                'status': 'error',
                'error': {'code': 'conflict', 'message': 'dup'},
            }
        )

        pd = player.plugin_data[PLUGIN_NAME]
        assert pd.is_duplicated is True
        assert pd.id is None
        assert counters.duplicate_count == 1

    def test_create_other_error_leaves_state_untouched_for_retry(
        self, session, builder, counters, monkeypatch
    ):
        local = make_sync_data(tid='T1')
        _patch_from_player(monkeypatch, local)
        player = make_player()

        session._plan_player_sync(player, None, builder, counters)
        builder.pending[0].on_error(
            {
                'index': 0,
                'status': 'error',
                'error': {'code': 'bad_request', 'message': 'oops'},
            }
        )

        pd = player.plugin_data[PLUGIN_NAME]
        assert pd.id is None
        assert pd.is_duplicated is False
        assert counters.duplicate_count == 0

    def test_soft_deleted_player_skipped(self, session, builder, counters):
        pd = SCEPlayerPluginData(id=None, deleted_id='SCE-OLD')
        player = make_player(plugin_data=pd)

        session._plan_player_sync(player, None, builder, counters)

        assert len(builder) == 0


# ── Branch C: 3-way merge ───────────────────────────────────────────────────


@pytest.mark.unit
class TestMergeBranch:
    def test_already_synced_no_op_no_save(
        self, session, builder, counters, monkeypatch
    ):
        last = make_sync_data(tid='T1', last_name='Doe')
        pd = SCEPlayerPluginData(id='SCE-1', last_sync_data=last)
        player = make_player(plugin_data=pd)
        local = make_sync_data(tid='T1', last_name='Doe')
        sce = make_sync_data(tid='T1', last_name='Doe')
        _patch_from_player(monkeypatch, local)

        session._plan_player_sync(player, sce, builder, counters)

        assert len(builder) == 0
        # last_sync_data unchanged
        assert player.plugin_data[PLUGIN_NAME].last_sync_data == last

    def test_modified_locally_queues_update_with_local_tournament_target(
        self, session, builder, counters, monkeypatch
    ):
        """op-level tournament_id must be TARGET (local), not
        source (sce). The batch endpoint reads tournament_id from op level —
        if equal to current, no move fires."""
        last = make_sync_data(tid='T1', last_name='Doe')
        pd = SCEPlayerPluginData(id='SCE-1', last_sync_data=last)
        player = make_player(plugin_data=pd)
        local = make_sync_data(tid='T2', last_name='Doe')  # MOVED locally
        sce = make_sync_data(tid='T1', last_name='Doe')  # unchanged on SC
        _patch_from_player(monkeypatch, local)

        session._plan_player_sync(player, sce, builder, counters)

        assert len(builder) == 1
        op = builder.pending[0]
        assert op.op_dict['op'] == 'update'
        assert op.op_dict['registration_id'] == 'SCE-1'
        # Target = local, not source. Triggers move on the server.
        assert op.op_dict['tournament_id'] == 'T2'

    def test_modified_locally_success_updates_last_sync(
        self, session, builder, counters, monkeypatch
    ):
        last = make_sync_data(tid='T1', last_name='Doe')
        pd = SCEPlayerPluginData(id='SCE-1', last_sync_data=last)
        player = make_player(plugin_data=pd)
        local = make_sync_data(tid='T1', last_name='Smith')
        sce = make_sync_data(tid='T1', last_name='Doe')
        _patch_from_player(monkeypatch, local)

        session._plan_player_sync(player, sce, builder, counters)
        builder.pending[0].on_success({'index': 0, 'status': 'ok'})

        assert player.plugin_data[PLUGIN_NAME].last_sync_data == local

    def test_modified_on_sc_pulls_locally_no_op_queued(
        self, session, builder, counters, monkeypatch
    ):
        last = make_sync_data(tid='T1', last_name='Doe')
        pd = SCEPlayerPluginData(id='SCE-1', last_sync_data=last)
        player = make_player(plugin_data=pd)
        local = make_sync_data(tid='T1', last_name='Doe')
        sce = make_sync_data(tid='T1', last_name='Smith')  # SC changed
        _patch_from_player(monkeypatch, local)

        session._plan_player_sync(player, sce, builder, counters)

        assert len(builder) == 0
        session.update_local_player.assert_called_once_with(player, sce)
        assert player.plugin_data[PLUGIN_NAME].last_sync_data == sce

    def test_both_mergeable_queues_update_with_merged_tournament_target(
        self, session, builder, counters, monkeypatch
    ):
        """Regression: when merge handles a tournament change, op-level
        tournament_id must come from MERGED data (which carries the local
        tournament_id since SC matched ref on that field)."""
        last = make_sync_data(tid='T1', last_name='Doe', club='Old')
        pd = SCEPlayerPluginData(id='SCE-1', last_sync_data=last)
        player = make_player(plugin_data=pd)
        # Local moved to T2, SC changed club. Mergeable.
        local = make_sync_data(tid='T2', last_name='Doe', club='Old')
        sce = make_sync_data(tid='T1', last_name='Doe', club='New')
        _patch_from_player(monkeypatch, local)

        session._plan_player_sync(player, sce, builder, counters)

        assert len(builder) == 1
        op = builder.pending[0]
        assert op.op_dict['op'] == 'update'
        # Merged carries local tournament_id (T2) + sc club (New).
        assert op.op_dict['tournament_id'] == 'T2'
        assert op.op_dict['data']['club'] == 'New'
        assert op.op_dict['data']['last_name'] == 'Doe'

    def test_both_unmergeable_sets_conflict_no_op_queued(
        self, session, builder, counters, monkeypatch
    ):
        """Regression: same field changed on both ends must register
        conflict, not silently overwrite local."""
        last = make_sync_data(tid='T1', last_name='Doe')
        pd = SCEPlayerPluginData(id='SCE-1', last_sync_data=last)
        player = make_player(plugin_data=pd)
        local = make_sync_data(tid='T1', last_name='Smith')  # local edit
        sce = make_sync_data(tid='T1', last_name='Jones')  # different SC edit
        _patch_from_player(monkeypatch, local)

        session._plan_player_sync(player, sce, builder, counters)

        assert len(builder) == 0  # No op queued — conflict only.
        assert counters.conflict_count == 1
        result_pd = player.plugin_data[PLUGIN_NAME]
        assert result_pd.conflict_sync_data == sce
        # Local user changes preserved (stored_player not mutated).
        session.update_local_player.assert_not_called()

    def test_merge_success_updates_local_and_last_sync(
        self, session, builder, counters, monkeypatch
    ):
        last = make_sync_data(tid='T1', last_name='Doe', club='Old')
        pd = SCEPlayerPluginData(id='SCE-1', last_sync_data=last)
        player = make_player(plugin_data=pd)
        local = make_sync_data(tid='T1', last_name='Smith', club='Old')
        sce = make_sync_data(tid='T1', last_name='Doe', club='New')
        _patch_from_player(monkeypatch, local)

        session._plan_player_sync(player, sce, builder, counters)
        builder.pending[0].on_success({'index': 0, 'status': 'ok'})

        # update_local_player called with merged data.
        assert session.update_local_player.call_count == 1
        merged = session.update_local_player.call_args[0][1]
        assert merged.last_name == 'Smith'
        assert merged.club == 'New'
        assert player.plugin_data[PLUGIN_NAME].last_sync_data == merged


# ── Tournament-force branch ─────────────────────────────────────────────────


@pytest.mark.unit
class TestTournamentForce:
    def test_paired_player_in_different_tournament_queues_force_update(
        self, session, builder, counters, monkeypatch
    ):
        last = make_sync_data(tid='T1', last_name='Doe')
        pd = SCEPlayerPluginData(id='SCE-1', last_sync_data=last)
        player = make_player(plugin_data=pd, has_real_pairings=True)
        local = make_sync_data(tid='T1', last_name='Doe')  # local stayed in T1
        sce = make_sync_data(tid='T2', last_name='Doe')  # SC moved to T2
        _patch_from_player(monkeypatch, local)

        session._plan_player_sync(player, sce, builder, counters)

        # Force update queued with target = local (T1).
        assert len(builder) >= 1
        force_op = builder.pending[0]
        assert force_op.op_dict['op'] == 'update'
        assert force_op.op_dict['registration_id'] == 'SCE-1'
        assert force_op.op_dict['tournament_id'] == 'T1'
