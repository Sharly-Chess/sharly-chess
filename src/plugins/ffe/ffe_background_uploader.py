from dataclasses import dataclass
from enum import IntEnum
from functools import partial
from threading import Thread

from common import format_timestamp_date_time
from common.i18n import _
from data.event import Event
from data.tournament import Tournament
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_session import FFESession
from plugins.utils import PluginUtils
from utils.enum import NeedsUpload

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
    uploading: bool = False
    upload_status_messages: dict[str, FfeUploadResult] = {}
    timeout_threads: dict[str, Thread] = {}

    @classmethod
    def result_id(cls, tournament: Tournament) -> str:
        return f'{tournament.event.uniq_id}:{tournament.id}'

    @classmethod
    def print_success(cls, tournament: Tournament, message: str) -> None:
        cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
            FfeUploadStatus.SUCCESS, message
        )

    @classmethod
    def print_error(cls, tournament: Tournament, message: str) -> None:
        cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
            FfeUploadStatus.ERROR, message
        )

    @classmethod
    def print_info(cls, tournament: Tournament, message: str) -> None:
        cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
            FfeUploadStatus.INFO, message
        )

    @classmethod
    def get_updated_upload_results(cls, admin_event: Event) -> list[Tournament]:
        tournaments: list[Tournament] = []
        for tournament in admin_event.tournaments_by_id.values():
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
                    _('FFE ID and password not defined for tournament').format(
                        tournament_uniq_id=tournament.uniq_id
                    ),
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
            else:
                tournaments.append(tournament)
        return tournaments

    @staticmethod
    def check_id_and_password(tournament: Tournament) -> bool:
        pd = tournament.plugin_data
        ffe_id = get_data(pd, 'ffe_id')
        ffe_password = get_data(pd, 'ffe_password')
        if not ffe_id or not ffe_password:
            print(
                _('FFE ID not defined for tournament [{tournament_uniq_id}].').format(
                    tournament_uniq_id=tournament.uniq_id
                )
            )
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
    def upload_event(cls, admin_event: Event) -> None:
        if cls.uploading:
            return
        cls.uploading = True

        tournaments = cls.get_updated_upload_results(admin_event)
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
            cls.uploading = False
            return

        for tournament in updated_tournaments:
            cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadResult(
                FfeUploadStatus.INFO,
                _('Uploading tournament...').format(
                    tournament_uniq_id=tournament.uniq_id
                ),
            )

        def _upload_tournaments(cls: FfeBackgroundUploader) -> None:
            try:
                for tournament in updated_tournaments:
                    FFESession(
                        tournament,
                        debug=False,
                        print_error=partial(
                            FfeBackgroundUploader.print_error, tournament
                        ),
                        print_info=partial(
                            FfeBackgroundUploader.print_info, tournament
                        ),
                        print_success=partial(
                            FfeBackgroundUploader.print_success, tournament
                        ),
                    ).upload(set_visible=False)
            finally:
                cls.uploading = False

        uploader = Thread(target=_upload_tournaments, args=(cls,))
        uploader.start()
