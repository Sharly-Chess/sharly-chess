from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import IntEnum
from functools import partial
from threading import Thread, Timer

from common.i18n import _, set_locale
from common.logger import (
    get_logger,
)
from common.network import NetworkMonitor
from common.sharly_chess_config import SharlyChessConfig
from data.loader import EventLoader
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredTournament, StoredEvent
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_session import FFESession
from plugins.ffe.utils import FFEUtils, FfeEventPluginData, FfeTournamentPluginData
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
    def result_id(cls, event_uniq_id: str, tournament_id: int) -> str:
        return f'{event_uniq_id}:{tournament_id}'

    @classmethod
    def get_updated_tournament_upload_result(
        cls, tournament: Tournament
    ) -> FfeUploadResult:
        result_id = cls.result_id(tournament.event.uniq_id, tournament.id)
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

        if unavailable_message := (
            FFEUtils.ffe_actions_unavailable_message(tournament)
        ):
            result = FfeUploadResult(
                FfeUploadStatus.SETTINGS_ERROR, unavailable_message
            )
            cls.upload_status_messages[result_id] = result
        elif (
            not FFEUtils.resolve_auto_upload(tournament)
            and result.status != FfeUploadStatus.NEVER
            and cls.ffe_upload_needed(tournament)
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
    def update_eligible_tournaments(
        cls, tournaments: list[Tournament]
    ) -> list[Tournament]:
        eligible_tournaments: list[Tournament] = []
        for tournament in tournaments:
            result = cls.get_updated_tournament_upload_result(tournament)
            if result.status == FfeUploadStatus.SETTINGS_ERROR:
                # Skip this tournament if we have a SETTINGS_ERROR
                continue

            eligible_tournaments.append(tournament)
        return eligible_tournaments

    @staticmethod
    def check_id_and_password(tournament: Tournament) -> bool:
        pd = FFEUtils.get_tournament_plugin_data(tournament)
        if not pd.ffe_id or not pd.password:
            return False
        return True

    @classmethod
    def ffe_last_upload(
        cls, tournament: Tournament | StoredTournament
    ) -> datetime | None:
        plugin_data: FfeTournamentPluginData
        if isinstance(tournament, Tournament):
            assert isinstance(tournament, Tournament)
            plugin_data = FFEUtils.get_tournament_plugin_data(tournament)
        else:
            raw_plugin_data = tournament.plugin_data.get(PLUGIN_NAME, {})
            plugin_data = FfeTournamentPluginData.from_stored_value(raw_plugin_data)

        return plugin_data.last_upload

    @classmethod
    def ffe_upload_needed(cls, tournament: Tournament | StoredTournament) -> bool:
        return (cls.ffe_last_upload(tournament) or datetime.min) < max(
            tournament.last_update or datetime.min,
            tournament.last_player_update or datetime.min,
            tournament.last_pairing_update or datetime.min,
        )

    @classmethod
    def publish_upload_event(cls):
        if channels_plugin:
            channels_plugin.publish(
                {
                    'event': 'upload-event',
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
        make_visible: bool = False,
    ) -> FfeUploadResult | None:
        """Upload a tournament to FFE."""

        # Set the locale (called in a new thread)
        set_locale(SharlyChessConfig().locale)

        # We refetch the latest event and tournament
        loader = EventLoader()
        if event_uniq_id not in loader.event_uniq_ids:
            # The event has been deleted
            return None
        event = loader.load_event(event_uniq_id)

        tournament = event.tournaments_by_id.get(tournament_id, None)
        if not tournament:
            # The tournament has been deleted
            return None

        current_result = cls.get_updated_tournament_upload_result(tournament)
        if current_result.status == FfeUploadStatus.SETTINGS_ERROR:
            # Skip this tournament if we now have a SETTINGS_ERROR
            return current_result

        result_id = cls.result_id(tournament.event.uniq_id, tournament.id)
        if (
            not force
            and not FFEUtils.resolve_auto_upload(tournament)
            and current_result.status != FfeUploadStatus.NEVER
        ):
            # Auto upload has been disabled since it was scheduled
            cls.upload_status_messages[result_id] = FfeUploadResult(
                FfeUploadStatus.CHANGED,
                _('Modified since last upload'),
            )
            return cls.upload_status_messages[result_id]

        if not NetworkMonitor.connected():
            # The network is offline, we can't upload
            cls.upload_status_messages[result_id] = FfeUploadResult(
                FfeUploadStatus.ERROR,
                _('Modified, but no internet connection'),
            )
            cls.publish_upload_event()
            return cls.upload_status_messages[result_id]

        cls.upload_status_messages[result_id] = FfeUploadResult(
            FfeUploadStatus.IN_PROGRESS,
            _('Uploading tournament…'),
        )

        logger.info('Uploading tournament [%s]...', tournament.name)

        def report(
            tournament_: Tournament, status: FfeUploadStatus, message: str
        ) -> None:
            cls.upload_status_messages[result_id] = FfeUploadResult(status, message)

        try:
            FFESession(
                tournament,
                report_error=partial(report, tournament, FfeUploadStatus.ERROR),
                report_info=partial(report, tournament, FfeUploadStatus.INFO),
                report_success=partial(report, tournament, FfeUploadStatus.SUCCESS),
            ).upload(set_visible=False)
        except Exception as e:
            logger.error('Error uploading tournament [%s]: [%s]', tournament.name, e)
            cls.upload_status_messages[result_id] = FfeUploadResult(
                FfeUploadStatus.ERROR,
                _('Error uploading tournament'),
            )
        finally:
            cls.publish_upload_event()

        return cls.upload_status_messages[result_id]

    @classmethod
    def upload_event_tournaments(cls, tournaments: list[Tournament]):
        if cls.uploading_event:
            return
        cls.uploading_event = True

        tournaments = cls.update_eligible_tournaments(tournaments)
        updated_tournaments: list[tuple[str, int]] = []
        for tournament in tournaments:
            if cls.ffe_upload_needed(tournament):
                updated_tournaments.append((tournament.event.uniq_id, tournament.id))
            else:
                cls.upload_status_messages[
                    cls.result_id(tournament.event.uniq_id, tournament.id)
                ] = FfeUploadResult(
                    FfeUploadStatus.INFO,
                    _('Tournament not modified since last upload'),
                )

        if not updated_tournaments:
            cls.uploading_event = False
            return

        for event_uuid, tournament_id in updated_tournaments:
            if not NetworkMonitor.connected():
                # The network is offline, we can't upload
                cls.upload_status_messages[cls.result_id(event_uuid, tournament_id)] = (
                    FfeUploadResult(
                        FfeUploadStatus.INFO,
                        _('No internet connection'),
                    )
                )
            else:
                cls.upload_status_messages[cls.result_id(event_uuid, tournament_id)] = (
                    FfeUploadResult(
                        FfeUploadStatus.IN_PROGRESS, _('Uploading tournament…')
                    )
                )

        def _upload_tournaments(cls_: FfeBackgroundUploader) -> None:
            try:
                # Set the locale (called in a new thread)
                set_locale(SharlyChessConfig().locale)
                for event_uuid_, tournament_id_ in updated_tournaments:
                    scheduled_upload = cls_.timeout_threads.get(
                        cls_.result_id(event_uuid_, tournament_id_)
                    )
                    if scheduled_upload and scheduled_upload.is_alive():
                        # Cancel the scheduled upload
                        scheduled_upload.cancel()
                        cls_.timeout_threads.pop(
                            cls_.result_id(event_uuid_, tournament_id_), None
                        )
                    cls_.upload_tournament(event_uuid_, tournament_id_, True)

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
        if stored_event.federation != 'FRA':
            return False

        # Check if the auto upload is enabled
        tournament_plugin_data = FfeTournamentPluginData.from_stored_value(
            stored_tournament.plugin_data.get(PLUGIN_NAME, {})
        )
        tournament_auto_upload = tournament_plugin_data.auto_upload
        if tournament_auto_upload is None:
            event_plugin_data = FfeEventPluginData.from_stored_value(
                stored_event.plugin_data.get(PLUGIN_NAME, {})
            )
            tournament_auto_upload = event_plugin_data.auto_upload
        if not tournament_auto_upload:
            return False

        assert stored_tournament.id is not None
        result_id = cls.result_id(stored_event.uniq_id, stored_tournament.id)
        thread = cls.timeout_threads.get(result_id)
        if thread and thread.is_alive():
            # There's already a thread running for this tournament
            return False

        if not cls.ffe_upload_needed(stored_tournament):
            # Latest version already uploaded
            return False

        return True

    @classmethod
    def schedule_upload(cls, tournament: Tournament, force=False) -> None:
        """Schedule the upload of a tournament that has been modified."""
        result = cls.get_updated_tournament_upload_result(tournament)
        if result.status == FfeUploadStatus.SETTINGS_ERROR:
            # Skip this tournament if we have a SETTINGS_ERROR
            return
        ffe_last_upload = cls.ffe_last_upload(tournament)
        delay = FFEUtils.resolve_auto_upload_delay(tournament.event)
        wait_time = 0.1
        result_id = cls.result_id(tournament.event.uniq_id, tournament.id)
        if (
            not force
            and ffe_last_upload
            and datetime.now() < ffe_last_upload + timedelta(minutes=delay)
        ):
            elapsed = (datetime.now() - ffe_last_upload).total_seconds()
            wait_time = max(delay * 60 - elapsed, 0.1)
            cls.upload_status_messages[result_id] = FfeUploadResult(
                FfeUploadStatus.PENDING, _('Tournament modified, awaiting auto-upload')
            )
        else:
            cls.upload_status_messages[result_id] = FfeUploadResult(
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
        cls.timeout_threads[result_id] = timer
        timer.start()
