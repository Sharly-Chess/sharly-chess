from dataclasses import dataclass
from enum import IntEnum
from functools import partial
from threading import Thread, Timer
from time import time

from common.i18n import _, set_locale
from common.logger import (
    get_logger,
)
from common.network import NetworkMonitor
from common.sharly_chess_config import SharlyChessConfig
from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredTournament, StoredEvent
from plugins.chess_results import PLUGIN_NAME
from plugins.chess_results.chess_results_session import ChessResultsSession
from plugins.chess_results.utils import ChessResultsUtils
from plugins.utils import PluginUtils
from web.channels import channels_plugin

logger = get_logger()
get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class ChessResultsUploadStatus(IntEnum):
    NEVER = 0
    UPLOADED = 1
    CHANGED = 2
    PENDING = 3
    IN_PROGRESS = 4
    SUCCESS = 5
    INFO = 6
    ERROR = 7
    SETTINGS_ERROR = 8


@dataclass
class ChessResultsUploadResult:
    status: ChessResultsUploadStatus
    message: str


class ChessResultsBackgroundUploader:
    uploading_event: bool = False
    upload_status_messages: dict[str, ChessResultsUploadResult] = {}
    timeout_threads: dict[str, Timer] = {}

    @classmethod
    def result_id(cls, event_uniq_id: str, tournament_id: int) -> str:
        return f'{event_uniq_id}:{tournament_id}'

    @classmethod
    def get_updated_tournament_upload_result(
        cls, tournament: Tournament
    ) -> ChessResultsUploadResult:
        result_id = cls.result_id(tournament.event.uniq_id, tournament.id)
        result = cls.upload_status_messages.get(result_id, None)

        # Clear the message if it is a SETTINGS_ERROR, and refresh it later...
        if result and result.status == ChessResultsUploadStatus.SETTINGS_ERROR:
            result = None

        # Default status when we don't have a result
        if result is None:
            if cls.chess_results_last_upload(tournament):
                result = ChessResultsUploadResult(
                    ChessResultsUploadStatus.UPLOADED,
                    _('Tournament previously uploaded.'),
                )
            else:
                result = ChessResultsUploadResult(
                    ChessResultsUploadStatus.NEVER,
                    _('Tournament not yet uploaded.'),
                )
            cls.upload_status_messages[result_id] = result

        if not ChessResultsUtils.resolve_auto_upload(
            tournament
        ) and cls.chess_results_upload_needed(tournament):
            # For manual updates tell the user that the tournament has been modified
            # For auto uploads, schedule_upload should have already an appropriate message
            result = ChessResultsUploadResult(
                ChessResultsUploadStatus.INFO,
                _('Modified since last upload'),
            )
            cls.upload_status_messages[result_id] = result
        return result

    @classmethod
    def update_eligible_tournaments(cls, admin_event: Event) -> list[Tournament]:
        tournaments: list[Tournament] = []
        for tournament in admin_event.tournaments_by_id.values():
            result = cls.get_updated_tournament_upload_result(tournament)
            if result.status == ChessResultsUploadStatus.SETTINGS_ERROR:
                # Skip this tournament if we have a SETTINGS_ERROR
                continue

            tournaments.append(tournament)
        return tournaments

    @classmethod
    def chess_results_last_upload(
        cls, tournament: Tournament | StoredTournament
    ) -> float:
        return get_data(tournament.plugin_data, 'last_upload', 0.0)

    @classmethod
    def chess_results_upload_needed(
        cls, tournament: Tournament | StoredTournament
    ) -> bool:
        return cls.chess_results_last_upload(tournament) < max(
            tournament.last_update,
            tournament.last_player_update,
            tournament.last_pairing_update,
        )

    @classmethod
    def publish_upload_event(cls):
        if channels_plugin:
            channels_plugin.publish(
                {
                    'event': 'chess-results-upload-event',
                    'data': '',
                },
                ['ws'],
            )

    @classmethod
    def upload_tournament(
        cls,
        event_uniq_id: str,
        tournament_id: int,
        force: bool,
    ) -> None:
        """Upload a tournament to Chess-Results.com."""

        # Set the locale (called in a new thread)
        set_locale(SharlyChessConfig().locale)

        # We refetch the latest event and tournament
        loader = EventLoader()
        if event_uniq_id not in loader.event_uniq_ids:
            # The event has been deleted
            return
        event = loader.load_event(event_uniq_id)

        tournament = event.tournaments_by_id.get(tournament_id, None)
        if not tournament:
            # The tournament has been deleted
            return

        current_result = cls.get_updated_tournament_upload_result(tournament)
        if current_result.status == ChessResultsUploadStatus.SETTINGS_ERROR:
            # Skip this tournament if we now have a SETTINGS_ERROR
            return

        result_id = cls.result_id(tournament.event.uniq_id, tournament.id)
        if not force and not ChessResultsUtils.resolve_auto_upload(tournament):
            # Auto upload has been disabled since it was scheduled
            cls.upload_status_messages[result_id] = ChessResultsUploadResult(
                ChessResultsUploadStatus.CHANGED,
                _('Modified since last upload'),
            )
            return

        if not NetworkMonitor.connected():
            # The network is offline, we can't upload
            cls.upload_status_messages[result_id] = ChessResultsUploadResult(
                ChessResultsUploadStatus.ERROR,
                _('Modified, but no internet connection'),
            )
            cls.publish_upload_event()
            return

        cls.upload_status_messages[result_id] = ChessResultsUploadResult(
            ChessResultsUploadStatus.IN_PROGRESS,
            _('Uploading tournament…'),
        )

        logger.info('Uploading tournament [%s]...', tournament.uniq_id)

        def report(
            tournament_: Tournament, status: ChessResultsUploadStatus, message: str
        ) -> None:
            cls.upload_status_messages[result_id] = ChessResultsUploadResult(
                status, message
            )

        try:
            tournament.compute_player_ranks()
            ChessResultsSession(
                tournament,
                report_error=partial(
                    report, tournament, ChessResultsUploadStatus.ERROR
                ),
                report_info=partial(report, tournament, ChessResultsUploadStatus.INFO),
                report_success=partial(
                    report, tournament, ChessResultsUploadStatus.SUCCESS
                ),
            ).upload()
        except Exception as e:
            logger.error('Error uploading tournament [%s]: [%s]', tournament.uniq_id, e)
            cls.upload_status_messages[result_id] = ChessResultsUploadResult(
                ChessResultsUploadStatus.ERROR,
                _('Error uploading tournament'),
            )
        finally:
            cls.publish_upload_event()

    @classmethod
    def upload_event(cls, admin_event: Event) -> None:
        if cls.uploading_event:
            return
        cls.uploading_event = True

        tournaments = cls.update_eligible_tournaments(admin_event)
        updated_tournaments: list[tuple[str, int]] = []
        for tournament in tournaments:
            if cls.chess_results_upload_needed(tournament):
                updated_tournaments.append((tournament.event.uniq_id, tournament.id))
            else:
                cls.upload_status_messages[
                    cls.result_id(tournament.event.uniq_id, tournament.id)
                ] = ChessResultsUploadResult(
                    ChessResultsUploadStatus.INFO,
                    _('Tournament not modified since last upload'),
                )

        if not updated_tournaments:
            cls.uploading_event = False
            return

        for event_uuid, tournament_id in updated_tournaments:
            if not NetworkMonitor.connected():
                # The network is offline, we can't upload
                cls.upload_status_messages[cls.result_id(event_uuid, tournament_id)] = (
                    ChessResultsUploadResult(
                        ChessResultsUploadStatus.INFO,
                        _('No internet connection'),
                    )
                )
            else:
                cls.upload_status_messages[cls.result_id(event_uuid, tournament_id)] = (
                    ChessResultsUploadResult(
                        ChessResultsUploadStatus.IN_PROGRESS, _('Uploading tournament…')
                    )
                )

        def _upload_tournaments(cls_: ChessResultsBackgroundUploader) -> None:
            try:
                # Set the locale (called in a new thread)
                set_locale(SharlyChessConfig().locale)
                for event_uuid, tournament_id in updated_tournaments:
                    scheduled_upload = cls_.timeout_threads.get(
                        cls_.result_id(event_uuid, tournament_id)
                    )
                    if scheduled_upload and scheduled_upload.is_alive():
                        # Cancel the scheduled upload
                        scheduled_upload.cancel()
                        cls_.timeout_threads.pop(
                            cls_.result_id(event_uuid, tournament_id), None
                        )
                    cls_.upload_tournament(event_uuid, tournament_id, True)

            finally:
                cls.uploading_event = False

        uploader = Thread(target=_upload_tournaments, args=(cls,))
        uploader.start()

    @classmethod
    def should_schedule_tournament_upload(
        cls,
        stored_event: StoredEvent,
        stored_tournament: StoredTournament,
    ) -> bool:
        # Check if the auto upload is enabled
        tournament_auto_upload = get_data(stored_tournament.plugin_data, 'auto_upload')
        if tournament_auto_upload is None:
            tournament_auto_upload = get_data(stored_event.plugin_data, 'auto_upload')
        if not tournament_auto_upload:
            return False

        assert stored_tournament.id is not None
        result_id = cls.result_id(stored_event.uniq_id, stored_tournament.id)
        thread = cls.timeout_threads.get(result_id)
        if thread and thread.is_alive():
            # There's already a thread running for this tournament
            return False

        if not cls.chess_results_upload_needed(stored_tournament):
            # Latest version already uploaded
            return False

        return True

    @classmethod
    def schedule_upload(cls, tournament: Tournament, force=False) -> None:
        """Schedule the upload of a tournament that has been modified."""
        result = cls.get_updated_tournament_upload_result(tournament)
        if result.status == ChessResultsUploadStatus.SETTINGS_ERROR:
            # Skip this tournament if we have a SETTINGS_ERROR
            return
        chess_results_last_upload = cls.chess_results_last_upload(tournament)
        delay = ChessResultsUtils.resolve_auto_upload_delay(tournament.event)
        wait_time = 0.1
        result_id = cls.result_id(tournament.event.uniq_id, tournament.id)
        if not force and time() < chess_results_last_upload + delay * 60:
            wait_time = max(delay * 60 - (time() - chess_results_last_upload), 0.1)
            cls.upload_status_messages[result_id] = ChessResultsUploadResult(
                ChessResultsUploadStatus.PENDING,
                _('Tournament modified, awaiting auto-upload'),
            )
        else:
            cls.upload_status_messages[result_id] = ChessResultsUploadResult(
                ChessResultsUploadStatus.IN_PROGRESS,
                _('Uploading tournament…'),
            )

        timer = Timer(
            wait_time,
            cls.upload_tournament,
            args=(
                tournament.event.uniq_id,
                tournament.id,
                force,
            ),
        )
        cls.timeout_threads[result_id] = timer
        timer.start()
