"""Background uploader for SCE tournament results."""

import time
from datetime import datetime, timedelta
from functools import partial
from threading import Thread, Timer

from common.i18n import set_locale
from common.logger import get_logger
from common.network import NetworkMonitor
from common.sharly_chess_config import SharlyChessConfig
from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredEvent, StoredTournament
from plugins.sce import PLUGIN_NAME, SCE_UPLOAD_DELAY
from plugins.sce.sce_session import SCESession
from plugins.sce.sce_tournament_results_builder import build_tournament_results
from plugins.sce.sce_tournament_status import (
    AuthFailureSCETournamentStatus,
    NetworkFailureSCETournamentStatus,
    NotFoundFailureSCETournamentStatus,
    UnexpectedFailureSCETournamentStatus,
    FailureSCETournamentStatus,
)
from plugins.sce.utils import SCEUtils
from plugins.utils import PluginUtils
from web.channels import channels_plugin

logger = get_logger()
get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


_ONGOING_TOURNAMENT_IDS: set[str] = set()
_TIMEOUT_THREADS: dict[str, Timer] = {}
_GROUP_UPLOAD_WAIT_QUEUE: set[str] = set()


def _result_key(event_uniq_id: str, tournament_id: int) -> str:
    return f'{event_uniq_id}:{tournament_id}'


def _tournament_result_key(tournament: Tournament) -> str:
    return f'{tournament.event.uniq_id}:{tournament.id}'


def is_upload_ongoing(tournament: Tournament) -> bool:
    """Return True if a background upload is currently running for this tournament."""
    key = _tournament_result_key(tournament)
    return key in _ONGOING_TOURNAMENT_IDS


def is_upload_scheduled(tournament: Tournament) -> bool:
    key = _tournament_result_key(tournament)
    thread = _TIMEOUT_THREADS.get(key)
    return bool(thread and thread.is_alive())


def is_upload_queued(tournament: Tournament) -> bool:
    key = _tournament_result_key(tournament)
    return key in _GROUP_UPLOAD_WAIT_QUEUE


def _publish_upload_event():
    if channels_plugin:
        channels_plugin.publish({'event': 'upload-event', 'data': ''}, ['ws'])


def upload_tournament(
    event_uniq_id: str,
    tournament_id: int,
):
    """Upload a tournament's results to the SCE platform. Runs in a background thread."""
    set_locale(SharlyChessConfig().locale)

    key = _result_key(event_uniq_id, tournament_id)
    _ONGOING_TOURNAMENT_IDS.add(key)
    _GROUP_UPLOAD_WAIT_QUEUE.discard(key)
    _publish_upload_event()

    # NOTE (Molrn) Ensures a minimum time for the thread
    # This prevents flashing and situations where both requests
    # triggered by the `upload-event` web socket are treated as one
    time.sleep(0.5)

    event: Event | None = None
    tournament: Tournament | None = None
    failure_status: FailureSCETournamentStatus | None = None
    try:
        loader = EventLoader()
        if event_uniq_id not in loader.event_uniq_ids:
            return
        event = loader.load_event(event_uniq_id)
        tournament = event.tournaments_by_id.get(tournament_id)
        if not tournament:
            return

        plugin_data = SCEUtils.get_tournament_plugin_data(tournament)
        sce_tournament_id = plugin_data.id
        if not sce_tournament_id:
            logger.warning(
                '%sNo SCE tournament ID set — skipping upload.',
                tournament.log_prefix,
            )
            return
        if not NetworkMonitor.connected():
            failure_status = NetworkFailureSCETournamentStatus()
            return

        event_plugin_data = SCEUtils.get_event_plugin_data(event)
        sce_event_id = event_plugin_data.id
        if not sce_event_id or not event_plugin_data.tokens:
            logger.warning(
                '%sNo SCE event credentials — skipping upload.',
                tournament.log_prefix,
            )
            return

        logger.info('%sUploading results to SCE…', tournament.log_prefix)
        payload = build_tournament_results(tournament, sce_event_id, sce_tournament_id)

        session = SCESession(event)
        status_code, body = session.upload_tournament_results(
            sce_tournament_id, payload
        )
        if status_code == 200:
            logger.info('%sSCE upload successful.', tournament.log_prefix)
        elif status_code == 404:
            failure_status = NotFoundFailureSCETournamentStatus()
            logger.error('%sSCE tournament not found (404).', tournament.log_prefix)
        else:
            failure_status = UnexpectedFailureSCETournamentStatus()
            logger.error(
                '%sSCE upload failed with HTTP %s: %s',
                tournament.log_prefix,
                status_code,
                body,
            )
    except Exception as e:
        failure_status = UnexpectedFailureSCETournamentStatus()
        if event and not SCEUtils.get_event_plugin_data(event).tokens:
            if tournament:
                failure_status = AuthFailureSCETournamentStatus()
        logger.exception(
            'Unexpected error uploading tournament [%s] to SC.com: %s',
            key,
            e,
        )
    finally:
        if tournament:
            plugin_data = SCEUtils.get_tournament_plugin_data(tournament)
            now = datetime.now()
            if failure_status:
                plugin_data.upload_failure_id = failure_status.id
            else:
                plugin_data.upload_failure_id = None
                plugin_data.last_upload_at = now
            plugin_data.last_upload_attempt_at = now
            SCEUtils.update_tournament_plugin_data(tournament, plugin_data)
        _ONGOING_TOURNAMENT_IDS.discard(key)
        _publish_upload_event()


def should_schedule_auto_upload(
    stored_event: StoredEvent,
    stored_tournament: StoredTournament,
) -> bool:
    # Check if the auto upload is enabled
    if not get_data(stored_event.plugin_data, 'auto_upload'):
        return False
    if not get_data(stored_tournament.plugin_data, 'auto_upload'):
        return False

    assert stored_tournament.id is not None
    key = _result_key(stored_event.uniq_id, stored_tournament.id)
    thread = _TIMEOUT_THREADS.get(key)
    if thread and thread.is_alive():
        # There's already a thread running for this tournament
        return False
    if not SCEUtils.tournament_modified_since_last_upload(stored_tournament):
        # Latest version already uploaded
        return False
    return True


def remove_scheduled_upload(tournament: Tournament):
    key = _tournament_result_key(tournament)
    thread = _TIMEOUT_THREADS.get(key)
    if thread and thread.is_alive():
        thread.cancel()


def schedule_upload(tournament: Tournament, force: bool = False):
    """Launch a background thread to upload this tournament's results."""
    if not tournament.started:
        return
    key = _tournament_result_key(tournament)
    if key in _ONGOING_TOURNAMENT_IDS:
        return

    last_upload_at = SCEUtils.get_tournament_last_upload(tournament)
    wait_time = 0.1
    if (
        not force
        and last_upload_at
        and datetime.now() < last_upload_at + timedelta(minutes=SCE_UPLOAD_DELAY)
    ):
        elapsed = (datetime.now() - last_upload_at).total_seconds()
        wait_time = max(SCE_UPLOAD_DELAY * 60 - elapsed, 0.1)

    timer = Timer(
        wait_time,
        upload_tournament,
        args=(tournament.event.uniq_id, tournament.id),
    )
    _TIMEOUT_THREADS[key] = timer
    timer.start()


def upload_event_tournaments(tournaments: list[Tournament]) -> None:
    """Upload all eligible SCE tournaments for an event in a background thread."""
    eligible = [
        tournament
        for tournament in tournaments
        if SCEUtils.get_tournament_plugin_data(tournament).id
        and tournament.started
        and _tournament_result_key(tournament) not in _ONGOING_TOURNAMENT_IDS
    ]
    if not eligible:
        return

    event_uniq_id = tournaments[0].event.uniq_id
    for tournament in eligible:
        _GROUP_UPLOAD_WAIT_QUEUE.add(_tournament_result_key(tournament))

    def _run() -> None:
        set_locale(SharlyChessConfig().locale)
        for tournament in eligible:
            upload_tournament(event_uniq_id, tournament.id)

    Thread(target=_run, daemon=True).start()
