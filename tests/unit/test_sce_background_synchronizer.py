"""Scheduling of the next background sync after one whose writes were
refused because another computer changed the registrations first."""

from unittest.mock import MagicMock

import pytest

from plugins.sce import sce_background_synchronizer
from plugins.sce.sce_sync_status import SuccessSCESyncStatus

EVENT_UNIQ_ID = 'test-sce-background-synchronizer'


@pytest.fixture
def run_sync(monkeypatch):
    """Runs `sync_event` with a session reporting `stale_count` stale ops,
    and returns the `schedule_sync` calls it made."""
    schedule_sync = MagicMock()
    event = MagicMock()
    event.uniq_id = EVENT_UNIQ_ID
    loader = MagicMock()
    loader.event_uniq_ids = [EVENT_UNIQ_ID]
    loader.load_event.return_value = event
    plugin_data = MagicMock()
    plugin_data.auto_player_sync = True
    monkeypatch.setattr(sce_background_synchronizer, 'time', MagicMock())
    monkeypatch.setattr(sce_background_synchronizer, 'EventLoader', lambda: loader)
    monkeypatch.setattr(sce_background_synchronizer, 'NetworkMonitor', MagicMock())
    monkeypatch.setattr(sce_background_synchronizer, '_exit_with_status', MagicMock())
    monkeypatch.setattr(
        sce_background_synchronizer, '_publish_upload_event', MagicMock()
    )
    monkeypatch.setattr(sce_background_synchronizer, 'schedule_sync', schedule_sync)
    sce_utils = MagicMock()
    sce_utils.get_event_plugin_data.return_value = plugin_data
    monkeypatch.setattr(sce_background_synchronizer, 'SCEUtils', sce_utils)
    monkeypatch.setattr(
        sce_background_synchronizer, '_STALE_RESYNC_EVENTS_UNIQ_IDS', set()
    )

    def run(stale_count: int) -> list:
        session = MagicMock()
        session.stale_count = stale_count
        session.sync_event.return_value = SuccessSCESyncStatus()
        monkeypatch.setattr(
            sce_background_synchronizer, 'SCESession', lambda _: session
        )
        schedule_sync.reset_mock()
        sce_background_synchronizer.sync_event(EVENT_UNIQ_ID)
        return [call.kwargs for call in schedule_sync.call_args_list]

    return run


@pytest.mark.unit
class TestStaleResync:
    def test_no_stale_op_waits_for_the_usual_delay(self, run_sync):
        assert run_sync(0) == [{}]

    def test_stale_ops_sync_again_at_once(self, run_sync):
        assert run_sync(2) == [{'force': True}]

    def test_the_immediate_resync_is_not_repeated(self, run_sync):
        run_sync(1)

        assert run_sync(1) == [{}]

    def test_a_later_sync_may_resync_at_once_again(self, run_sync):
        run_sync(1)
        run_sync(0)

        assert run_sync(1) == [{'force': True}]
