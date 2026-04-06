import time
from datetime import datetime, timedelta
from functools import partial
from threading import Thread, Timer

from common.i18n import set_locale
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
from plugins.ffe.ffe_upload_status import (
    FailureFFEUploadStatus,
    NetworkFailureFFEUploadStatus,
    UnexpectedFailureFFEUploadStatus,
)
from plugins.ffe.utils import (
    FFEUtils,
    FfeEventPluginData,
    FfeTournamentPluginData,
    FFE_UPLOAD_DELAY,
)
from plugins.utils import PluginUtils
from utils import Utils
from web.channels import channels_plugin

logger = get_logger()
get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class FfeBackgroundUploader:
    timeout_threads: dict[str, Timer] = {}
    group_upload_wait_queue: set[str] = set()
    ongoing_result_ids: set[str] = set()

    @staticmethod
    def result_id(event_uniq_id: str, tournament_id: int) -> str:
        return f'{event_uniq_id}:{tournament_id}'

    @classmethod
    def tournament_result_id(cls, tournament: Tournament) -> str:
        return cls.result_id(tournament.event.uniq_id, tournament.id)

    @classmethod
    def is_upload_ongoing(cls, tournament: Tournament) -> bool:
        """Return True if a background upload is currently running for this tournament."""
        key = cls.tournament_result_id(tournament)
        return key in cls.ongoing_result_ids

    @classmethod
    def is_upload_scheduled(cls, tournament: Tournament) -> bool:
        key = cls.tournament_result_id(tournament)
        thread = cls.timeout_threads.get(key)
        return bool(thread and thread.is_alive())

    @classmethod
    def is_upload_queued(cls, tournament: Tournament) -> bool:
        key = cls.tournament_result_id(tournament)
        return key in cls.group_upload_wait_queue

    @classmethod
    def remove_scheduled_upload(cls, tournament: Tournament):
        key = cls.tournament_result_id(tournament)
        thread = cls.timeout_threads.get(key)
        if thread and thread.is_alive():
            thread.cancel()

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

        return plugin_data.last_upload_at

    @classmethod
    def ffe_upload_needed(cls, tournament: Tournament | StoredTournament) -> bool:
        last_upload = cls.ffe_last_upload(tournament)
        return not last_upload or Utils.tournament_results_modified_since(
            tournament, last_upload
        )

    @classmethod
    def publish_upload_event(cls, start: bool = False):
        if channels_plugin:
            channels_plugin.publish(
                {
                    'event': f'upload-event{"-start" if start else ""}',
                    'data': '',
                },
                ['ws'],
            )

    @classmethod
    def upload_tournament(
        cls,
        event_uniq_id: str,
        tournament_id: int,
        set_visible: bool = False,
    ):
        """Upload a tournament to FFE."""

        # Set the locale (called in a new thread)
        set_locale(SharlyChessConfig().locale)
        result_id = cls.result_id(event_uniq_id, tournament_id)
        cls.ongoing_result_ids.add(result_id)
        cls.group_upload_wait_queue.discard(result_id)
        cls.publish_upload_event(start=True)

        # NOTE (Molrn) Ensures a minimum time for the thread
        # This prevents flashing and situations where both requests
        # triggered by the `upload-event` web socket are treated as one
        time.sleep(0.5)

        tournament: Tournament | None = None
        failure_status: FailureFFEUploadStatus | None = None
        try:
            loader = EventLoader()
            if event_uniq_id not in loader.event_uniq_ids:
                # The event has been deleted
                return
            event = loader.load_event(event_uniq_id)

            tournament = event.tournaments_by_id.get(tournament_id, None)
            if not tournament:
                # The tournament has been deleted
                return
            if FFEUtils.ffe_actions_unavailable_message(tournament):
                # Tournament can't be uploaded
                return

            if not NetworkMonitor.connected():
                failure_status = NetworkFailureFFEUploadStatus()
                return

            logger.info(
                'Uploading tournament [%s] to the FFE website...', tournament.name
            )
            failure_status = FFESession(tournament).upload(set_visible)
        except Exception as e:
            logger.exception('Error uploading tournament [%s]: [%s]', result_id, e)
            failure_status = UnexpectedFailureFFEUploadStatus()
        finally:
            cls.ongoing_result_ids.discard(result_id)
            if tournament:
                plugin_data = FFEUtils.get_tournament_plugin_data(tournament)
                now = datetime.now()
                if failure_status:
                    plugin_data.upload_failure_id = failure_status.id
                else:
                    plugin_data.upload_failure_id = None
                    plugin_data.last_upload_at = now
                plugin_data.last_upload_attempt_at = now
                FFEUtils.update_tournament_plugin_data(tournament, plugin_data)
            cls.publish_upload_event()

    @classmethod
    def upload_event_tournaments(cls, tournaments: list[Tournament]) -> None:
        """Upload all eligible SCE tournaments for an event in a background thread."""
        eligible = [
            tournament
            for tournament in tournaments
            if not FFEUtils.ffe_actions_unavailable_message(tournament)
            and cls.tournament_result_id(tournament) not in cls.ongoing_result_ids
        ]
        if not eligible:
            return

        event_uniq_id = tournaments[0].event.uniq_id
        for tournament in eligible:
            cls.group_upload_wait_queue.add(cls.tournament_result_id(tournament))

        def _run():
            set_locale(SharlyChessConfig().locale)
            for tournament in eligible:
                cls.upload_tournament(event_uniq_id, tournament.id)

        Thread(target=_run, daemon=True).start()

    @classmethod
    def should_schedule_tournament_upload(
        cls,
        stored_event: StoredEvent,
        stored_tournament: StoredTournament,
    ) -> bool:
        if stored_event.federation != 'FRA':
            return False

        # Check if the auto upload is enabled
        event_plugin_data = FfeEventPluginData.from_stored_value(
            stored_event.plugin_data.get(PLUGIN_NAME, {})
        )
        if not event_plugin_data.auto_upload:
            return False

        tournament_plugin_data = FfeTournamentPluginData.from_stored_value(
            stored_tournament.plugin_data.get(PLUGIN_NAME, {})
        )
        if not tournament_plugin_data.auto_upload:
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
    def schedule_upload(cls, tournament: Tournament, force=False):
        """Schedule the upload of a tournament that has been modified."""
        if FFEUtils.ffe_actions_unavailable_message(tournament):
            return

        ffe_last_upload = cls.ffe_last_upload(tournament)
        delay = FFE_UPLOAD_DELAY
        wait_time = 0.1
        result_id = cls.result_id(tournament.event.uniq_id, tournament.id)
        if (
            not force
            and ffe_last_upload
            and datetime.now() < ffe_last_upload + timedelta(minutes=delay)
        ):
            elapsed = (datetime.now() - ffe_last_upload).total_seconds()
            wait_time = max(delay * 60 - elapsed, 0.1)

        timer = Timer(
            wait_time,
            cls.upload_tournament,
            args=(
                tournament.event.uniq_id,
                tournament.id,
            ),
        )
        cls.timeout_threads[result_id] = timer
        timer.start()
