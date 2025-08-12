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
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_session import FFESession
from plugins.ffe.utils import FFEUtils
from plugins.utils import PluginUtils
from web.channels import channels_plugin

logger = get_logger()
get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class FfeUploadStatus(IntEnum):
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
class FfeUploadResult:
    status: FfeUploadStatus
    message: str


class FfeBackgroundUploader:
    uploading_event: bool = False
    upload_status_messages: dict[str, FfeUploadResult] = {}
    timeout_threads: dict[str, Timer] = {}

    @classmethod
    def result_id(cls, tournament: Tournament) -> str:
        return f'{tournament.event.uniq_id}:{tournament.id}'

    @classmethod
    def get_updated_tournament_upload_result(
        cls, tournament: Tournament
    ) -> FfeUploadResult:
        result_id = cls.result_id(tournament)
        result = cls.upload_status_messages.get(result_id, None)

        # Clear the message if it is a SETTINGS_ERROR, and refresh it later...
        if result and result.status == FfeUploadStatus.SETTINGS_ERROR:
            result = None

        # Default status when we don't have a result
        if result is None:
            if cls.ffe_last_upload(tournament):
                result = FfeUploadResult(
                    FfeUploadStatus.UPLOADED,
                    _('Tournament previously uploaded.'),
                )
            else:
                result = FfeUploadResult(
                    FfeUploadStatus.NEVER,
                    _('Tournament not yet uploaded.'),
                )
            cls.upload_status_messages[result_id] = result

        if not cls.check_id_and_password(tournament):
            result = FfeUploadResult(
                FfeUploadStatus.SETTINGS_ERROR,
                _('FFE certification number and password not defined for tournament.'),
            )
            cls.upload_status_messages[result_id] = result
        elif not FFEUtils.resolve_auto_upload(tournament) and cls.ffe_upload_needed(
            tournament
        ):
            # For manual updates tell the user that the tournament has been modified
            # For auto uploads, schedule_upload should have already an appropriate message
            result = FfeUploadResult(
                FfeUploadStatus.INFO,
                _('Modified since last upload'),
            )
            cls.upload_status_messages[result_id] = result
        return result

    @classmethod
    def update_eligible_tournaments(cls, admin_event: Event) -> list[Tournament]:
        tournaments: list[Tournament] = []
        for tournament in admin_event.tournaments_by_id.values():
            result = cls.get_updated_tournament_upload_result(tournament)
            if result.status == FfeUploadStatus.SETTINGS_ERROR:
                # Skip this tournament if we have a SETTINGS_ERROR
                continue

            tournaments.append(tournament)
        return tournaments

    @staticmethod
    def check_id_and_password(tournament: Tournament) -> bool:
        pd = tournament.plugin_data
        ffe_id = get_data(pd, 'ffe_id')
        ffe_password = get_data(pd, 'ffe_password')
        if not ffe_id or not ffe_password:
            return False
        return True

    @classmethod
    def ffe_last_upload(cls, tournament: Tournament) -> float:
        return get_data(tournament.plugin_data, 'ffe_last_upload', 0.0)

    @classmethod
    def ffe_upload_needed(cls, tournament: Tournament) -> bool:
        return cls.ffe_last_upload(tournament) < max(
            tournament.last_update,
            tournament.last_player_update,
            tournament.last_pairing_update,
        )

    @classmethod
    def publish_upload_event(cls):
        if channels_plugin:
            channels_plugin.publish(
                {
                    'event': 'ffe-upload-event',
                    'data': '',
                },
                ['sse'],
            )

    @classmethod
    def upload_tournament(
        cls,
        event_uniq_id: str,
        tournament_id: int,
        force: bool,
        make_visible: bool = False,
    ) -> None:
        """Upload a tournament to FFE."""

        # Set the locale (called in a new thread)
        set_locale(SharlyChessConfig().locale)

        # We refetch the latest event and tournament
        event = EventLoader().events_by_id.get(event_uniq_id, None)
        if not event:
            # The event has been deleted
            return

        tournament = event.tournaments_by_id.get(tournament_id, None)
        if not tournament:
            # The tournament has been deleted
            return

        current_result = cls.get_updated_tournament_upload_result(tournament)
        if current_result.status == FfeUploadStatus.SETTINGS_ERROR:
            # Skip this tournament if we now have a SETTINGS_ERROR
            return

        if not force and not FFEUtils.resolve_auto_upload(tournament):
            # Auto upload has been disabled since it was scheduled
            cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
                FfeUploadStatus.CHANGED,
                _('Modified since last upload'),
            )
            return

        if not NetworkMonitor.connected():
            # The network is offline, we can't upload
            cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
                FfeUploadStatus.ERROR,
                _('Modified, but no internet connection'),
            )
            cls.publish_upload_event()
            return

        cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
            FfeUploadStatus.IN_PROGRESS,
            _('Uploading tournament…'),
        )

        logger.info('Uploading tournament [%s]...', tournament.uniq_id)

        def report(
            tournament_: Tournament, status: FfeUploadStatus, message: str
        ) -> None:
            cls.upload_status_messages[cls.result_id(tournament_)] = FfeUploadResult(
                status, message
            )

        try:
            FFESession(
                tournament,
                report_error=partial(report, tournament, FfeUploadStatus.ERROR),
                report_info=partial(report, tournament, FfeUploadStatus.INFO),
                report_success=partial(report, tournament, FfeUploadStatus.SUCCESS),
            ).upload(set_visible=False)
        except Exception as e:
            logger.error('Error uploading tournament [%s]: [%s]', tournament.uniq_id, e)
            cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
                FfeUploadStatus.ERROR,
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
        updated_tournaments: list[Tournament] = []
        for tournament in tournaments:
            if cls.ffe_upload_needed(tournament):
                updated_tournaments.append(tournament)
            else:
                cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
                    FfeUploadStatus.INFO,
                    _('Tournament not modified since last upload'),
                )

        if not updated_tournaments:
            cls.uploading_event = False
            return

        for tournament in updated_tournaments:
            if not NetworkMonitor.connected():
                # The network is offline, we can't upload
                cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
                    FfeUploadStatus.INFO,
                    _('No internet connection'),
                )
            else:
                cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
                    FfeUploadStatus.IN_PROGRESS, _('Uploading tournament…')
                )

        def _upload_tournaments(cls_: FfeBackgroundUploader) -> None:
            try:
                # Set the locale (called in a new thread)
                set_locale(SharlyChessConfig().locale)
                for tournament_ in updated_tournaments:
                    scheduled_upload = cls_.timeout_threads.get(
                        cls_.result_id(tournament_)
                    )
                    if scheduled_upload and scheduled_upload.is_alive():
                        # Cancel the scheduled upload
                        scheduled_upload.cancel()
                        cls_.timeout_threads.pop(cls_.result_id(tournament_), None)
                    cls_.upload_tournament(
                        tournament_.event.uniq_id, tournament_.id, True
                    )

            finally:
                cls.uploading_event = False

        uploader = Thread(target=_upload_tournaments, args=(cls,))
        uploader.start()

    @classmethod
    def schedule_upload(cls, tournament: Tournament, force=False) -> None:
        """Schedule the upload of a tournament that has been modified."""

        if not force:
            result = cls.get_updated_tournament_upload_result(tournament)
            if result.status == FfeUploadStatus.SETTINGS_ERROR:
                # Skip this tournament if we have a SETTINGS_ERROR
                return

            if not cls.ffe_upload_needed(tournament):
                # Latest version already uploaded
                return

            thread = cls.timeout_threads.get(cls.result_id(tournament))
            if thread and thread.is_alive():
                # There's already a thread running for this tournament
                return

        ffe_last_upload = cls.ffe_last_upload(tournament)
        delay = FFEUtils.resolve_auto_upload_delay(tournament.event)
        wait_time = 0.1
        if not force and time() < ffe_last_upload + delay * 60:
            wait_time = max(delay * 60 - (time() - ffe_last_upload), 0.1)
            cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
                FfeUploadStatus.PENDING, _('Tournament modified, awaiting auto-upload')
            )
        else:
            cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
                FfeUploadStatus.IN_PROGRESS,
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
        cls.timeout_threads[cls.result_id(tournament)] = timer
        timer.start()
