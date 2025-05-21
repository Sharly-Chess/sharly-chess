from dataclasses import dataclass
from enum import IntEnum
from functools import partial
from threading import Thread, Timer
from time import time

from common import format_timestamp_date_time
from common.i18n import _
from common.logger import (
    get_logger,
)
from common.network import NetworkMonitor
from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_session import FFESession
from plugins.ffe.utils import FFEUtils
from plugins.utils import PluginUtils
from utils.enum import NeedsUpload

logger = get_logger()
get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class FfeUploadStatus(IntEnum):
    SUCCESS = 0
    INFO = 1
    ERROR = 2
    SETTINGS_ERROR = 3


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
    def report_success(cls, tournament: Tournament, message: str) -> None:
        cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
            FfeUploadStatus.SUCCESS, message
        )

    @classmethod
    def report_error(cls, tournament: Tournament, message: str) -> None:
        cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
            FfeUploadStatus.ERROR, message
        )

    @classmethod
    def report_info(cls, tournament: Tournament, message: str) -> None:
        cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
            FfeUploadStatus.INFO, message
        )

    @classmethod
    def get_updated_tournament_upload_result(
        cls, tournament: Tournament
    ) -> FfeUploadResult | None:
        result_id = cls.result_id(tournament)
        result = (
            cls.upload_status_messages[result_id]
            if result_id in cls.upload_status_messages
            else None
        )

        # Clear the message if it is a SETTINGS_ERROR, and refresh it here...
        if result and result.status == FfeUploadStatus.SETTINGS_ERROR:
            result.message = ''
        if not cls.check_id_and_password(tournament):
            cls.upload_status_messages[result_id] = FfeUploadResult(
                FfeUploadStatus.SETTINGS_ERROR,
                _(
                    'FFE certification number and password not defined for tournament'
                ).format(tournament_uniq_id=tournament.uniq_id),
            )
            pass
        elif not tournament.file:
            cls.upload_status_messages[result_id] = FfeUploadResult(
                FfeUploadStatus.SETTINGS_ERROR,
                _('Papi file not defined for tournament').format(
                    tournament_uniq_id=tournament.uniq_id
                ),
            )
        elif not tournament.file_exists:
            cls.upload_status_messages[result_id] = FfeUploadResult(
                FfeUploadStatus.SETTINGS_ERROR,
                _('Papi file not found [{file}]').format(
                    file=tournament.file, tournament_uniq_id=tournament.uniq_id
                ),
            )

        return result

    @classmethod
    def update_eligible_tournaments(cls, admin_event: Event) -> list[Tournament]:
        tournaments: list[Tournament] = []
        for tournament in admin_event.tournaments_by_id.values():
            result = cls.get_updated_tournament_upload_result(tournament)
            if result and result.status == FfeUploadStatus.SETTINGS_ERROR:
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
    def ffe_upload_needed(cls, tournament: Tournament) -> NeedsUpload:
        try:
            ffe_last_upload = cls.ffe_last_upload(tournament)
            if ffe_last_upload > tournament.file_modified_timestamp:
                # Last version already uploaded
                return NeedsUpload.NO_CHANGE
            return NeedsUpload.YES
        except FileNotFoundError:
            return NeedsUpload.NO_CHANGE

    @classmethod
    def upload_tournament(
        cls, event_uniq_id: str, tournament_id: int, force: bool
    ) -> None:
        """Upload a tournament to FFE."""

        if not NetworkMonitor.connected():
            # The network is offline, we can't upload
            return

        # We refetch the latest event and tournament
        event = EventLoader().events_by_id.get(event_uniq_id, None)
        if not event:
            # The event has been deleted
            return

        tournament = event.tournaments_by_id.get(tournament_id, None)
        if not tournament:
            # The tournament has been deleted
            return

        if not force and not FFEUtils.resolve_auto_upload(tournament):
            # Auto upload has been disabled since it was scheduled
            return

        current_result = cls.get_updated_tournament_upload_result(tournament)
        if current_result and current_result.status == FfeUploadStatus.SETTINGS_ERROR:
            # Skip this tournament if we have a SETTINGS_ERROR
            return

        logger.info(
            'Uploading tournament [{tournament_uniq_id}]...'.format(
                tournament_uniq_id=tournament.uniq_id
            )
        )
        try:
            FFESession(
                tournament,
                debug=False,
                report_error=partial(FfeBackgroundUploader.report_error, tournament),
                report_info=partial(FfeBackgroundUploader.report_info, tournament),
                report_success=partial(
                    FfeBackgroundUploader.report_success, tournament
                ),
            ).upload(set_visible=False)
        except Exception as e:
            if not tournament.event:
                # The event has been deleted
                return

            logger.error(
                'Error uploading tournament [{tournament_uniq_id}]: {error}'
            ).format(tournament_uniq_id=tournament.uniq_id, error=str(e))
            cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
                FfeUploadStatus.ERROR,
                _('Error uploading tournament'),
            )

    @classmethod
    def upload_event(cls, admin_event: Event) -> None:
        if cls.uploading_event:
            return
        cls.uploading_event = True

        tournaments = cls.update_eligible_tournaments(admin_event)
        updated_tournaments: list[Tournament] = []
        for tournament in tournaments:
            needs_upload: NeedsUpload = cls.ffe_upload_needed(tournament)
            match needs_upload:
                case NeedsUpload.YES:
                    updated_tournaments.append(tournament)
                case NeedsUpload.NO_CHANGE:
                    cls.upload_status_messages[cls.result_id(tournament)] = (
                        FfeUploadResult(
                            FfeUploadStatus.INFO,
                            _('Papi file not modified since last upload').format(
                                last_upload=format_timestamp_date_time(
                                    cls.ffe_last_upload(tournament)
                                )
                            ),
                        )
                    )
                    pass

        if not updated_tournaments:
            cls.uploading_event = False
            return

        for tournament in updated_tournaments:
            if not NetworkMonitor.connected():
                # The network is offline, we can't upload
                cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
                    FfeUploadStatus.INFO,
                    _('Network is offline, unable to upload tournament'),
                )
            else:
                cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
                    FfeUploadStatus.INFO,
                    _('Uploading tournament...').format(
                        tournament_uniq_id=tournament.uniq_id
                    ),
                )

        def _upload_tournaments(cls: FfeBackgroundUploader) -> None:
            try:
                for tournament in updated_tournaments:
                    scheduled_upload = cls.timeout_threads.get(
                        cls.result_id(tournament)
                    )
                    if scheduled_upload and scheduled_upload.is_alive():
                        # Cancel the scheduled upload
                        scheduled_upload.cancel()
                        cls.timeout_threads.pop(cls.result_id(tournament), None)
                    cls.upload_tournament(tournament.event.uniq_id, tournament.id, True)

            finally:
                cls.uploading_event = False

        uploader = Thread(target=_upload_tournaments, args=(cls,))
        uploader.start()

    @classmethod
    def schedule_upload(cls, tournament: Tournament) -> None:
        """Schedule the upload of a tournament that has been modified."""

        result = cls.get_updated_tournament_upload_result(tournament)
        if result and result.status == FfeUploadStatus.SETTINGS_ERROR:
            # Skip this tournament if we have a SETTINGS_ERROR
            return

        ffe_last_upload = cls.ffe_last_upload(tournament)
        if ffe_last_upload > tournament.file_modified_timestamp:
            # Latest version already uploaded
            return

        thread = cls.timeout_threads.get(cls.result_id(tournament))
        if thread and thread.is_alive():
            # There's already a thread running for this tournament
            return

        delay = get_data(tournament.event.plugin_data, 'ffe_upload_delay', 3)
        wait_time = (
            max(delay * 60 - (time() - ffe_last_upload), 0)
            if time() < ffe_last_upload + delay * 60
            else 0.1
        )

        timer = Timer(
            wait_time,
            cls.upload_tournament,
            args=(
                tournament.event.uniq_id,
                tournament.id,
                False,
            ),
        )
        cls.timeout_threads[cls.result_id(tournament)] = timer
        timer.start()
