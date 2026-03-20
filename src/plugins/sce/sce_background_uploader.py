"""Background uploader for SCE tournament results."""

from datetime import datetime, timedelta
from functools import partial
from threading import Thread, Timer

from common.i18n import set_locale
from common.logger import get_logger
from common.network import NetworkMonitor
from common.sharly_chess_config import SharlyChessConfig
from data.loader import EventLoader
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredEvent, StoredTournament
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_session import SCESession, SCE_UPLOAD_DELAY
from plugins.sce.sce_tournament_results_builder import build_tournament_results
from plugins.sce.sce_tournament_status import (
    AuthFailureSCETournamentStatus,
    NetworkFailureSCETournamentStatus,
    NotFoundFailureSCETournamentStatus,
    SuccessSCETournamentStatus,
    UnexpectedHTTPFailureSCETournamentStatus,
    SCETournamentStatus,
)
from plugins.sce.utils import SCEUtils, SCETournamentPluginData
from plugins.utils import PluginUtils
from web.channels import channels_plugin

logger = get_logger()
get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


_ONGOING_TOURNAMENT_IDS: set[str] = set()
_TIMEOUT_THREADS: dict[str, Timer] = {}


def _result_key(event_uniq_id: str, tournament_id: int) -> str:
    return f'{event_uniq_id}:{tournament_id}'


def _tournament_result_key(tournament: Tournament) -> str:
    return f'{tournament.event.uniq_id}:{tournament.id}'


def is_upload_ongoing(tournament: Tournament) -> bool:
    """Return True if a background upload is currently running for this tournament."""
    key = _tournament_result_key(tournament)
    return key in _ONGOING_TOURNAMENT_IDS


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
    _publish_upload_event()

    event = None
    tournament = None
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
            _set_upload_status(tournament, NetworkFailureSCETournamentStatus())
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
            _set_upload_status(
                tournament,
                SuccessSCETournamentStatus(),
                last_upload_at=datetime.now(),
            )
            logger.info('%sSCE upload successful.', tournament.log_prefix)
        elif status_code == 404:
            _set_upload_status(tournament, NotFoundFailureSCETournamentStatus())
            logger.error('%sSCE tournament not found (404).', tournament.log_prefix)
        else:
            _set_upload_status(tournament, UnexpectedHTTPFailureSCETournamentStatus())
            logger.error(
                '%sSCE upload failed with HTTP %s: %s',
                tournament.log_prefix,
                status_code,
                body,
            )
    except Exception:
        if event is not None and not SCEUtils.get_event_plugin_data(event).tokens:
            if tournament is not None:
                _set_upload_status(tournament, AuthFailureSCETournamentStatus())
            return
        if tournament is not None:
            _set_upload_status(tournament, UnexpectedHTTPFailureSCETournamentStatus())
        logger.exception(
            'Unexpected error uploading tournament [%s/%s] to SCE.',
            event_uniq_id,
            tournament_id,
        )
    finally:
        _ONGOING_TOURNAMENT_IDS.discard(key)
        _publish_upload_event()


def _set_upload_status(
    tournament: Tournament,
    status: SCETournamentStatus,
    last_upload_at: datetime | None = None,
) -> None:
    plugin_data: SCETournamentPluginData = SCEUtils.get_tournament_plugin_data(
        tournament
    )
    plugin_data.upload_status = status.id
    if last_upload_at is not None:
        plugin_data.last_upload_at = last_upload_at
    SCEUtils.update_tournament_plugin_data(tournament, plugin_data)


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
    key = _tournament_result_key(tournament)
    _TIMEOUT_THREADS[key] = timer
    timer.start()


def upload_event_tournaments(tournaments: list[Tournament]) -> None:
    """Upload all eligible SCE tournaments for an event in a background thread."""
    eligible = [
        t
        for t in tournaments
        if SCEUtils.get_tournament_plugin_data(t).id
        and t.started
        and _tournament_result_key(t) not in _ONGOING_TOURNAMENT_IDS
    ]
    if not eligible:
        return

    def _run() -> None:
        set_locale(SharlyChessConfig().locale)
        for t in eligible:
            upload_tournament(t.event.uniq_id, t.id)

    Thread(target=_run, daemon=True).start()
