from functools import partial

from data.tournament import Tournament
from plugins.chessevent import PLUGIN_NAME
from plugins.utils import PluginUtils
from plugins.chessevent.chessevent_status import (
    ChessEventStatus,
    UnsetChessEventStatus,
    EventSettingsErrorChessEventStatus,
    UserSettingsErrorChessEventStatus,
    PasswordSettingsErrorChessEventStatus,
    StartedChessEventStatus,
    NeverSyncedChessEventStatus,
    SuccessChessEventStatus,
    ConnectionErrorChessEventStatus,
    AuthErrorChessEventStatus,
    UnauthorizedErrorChessEventStatus,
    EventNotFoundChessEventStatus,
    TournamentNotFoundChessEventStatus,
    UnexpectedErrorChessEventStatus,
)
from utils.entity import EntityManager

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class ChessEventUtils:
    @staticmethod
    def resolve_user_id(tournament: Tournament) -> str | None:
        if chessevent_user_id := get_data(tournament.plugin_data, 'chessevent_user_id'):
            return chessevent_user_id
        return get_data(tournament.event.plugin_data, 'chessevent_user_id')

    @staticmethod
    def resolve_password(tournament: Tournament) -> str | None:
        if chessevent_password := get_data(
            tournament.plugin_data, 'chessevent_password'
        ):
            return chessevent_password
        return get_data(tournament.event.plugin_data, 'chessevent_password')

    @staticmethod
    def resolve_event_id(tournament: Tournament) -> str | None:
        if chessevent_event_id := get_data(
            tournament.plugin_data, 'chessevent_event_id'
        ):
            return chessevent_event_id
        return get_data(tournament.event.plugin_data, 'chessevent_event_id')

    @staticmethod
    def resolve_tournament_name(tournament: Tournament) -> str | None:
        return get_data(tournament.plugin_data, 'chessevent_tournament_name')

    @classmethod
    def resolve_tournament_status(cls, tournament: Tournament) -> ChessEventStatus:
        if not cls.resolve_tournament_name(tournament):
            return UnsetChessEventStatus()
        if tournament.started:
            return StartedChessEventStatus()
        if not cls.resolve_event_id(tournament):
            return EventSettingsErrorChessEventStatus()
        if not cls.resolve_user_id(tournament):
            return UserSettingsErrorChessEventStatus()
        if not cls.resolve_password(tournament):
            return PasswordSettingsErrorChessEventStatus()
        status_id = get_data(tournament.plugin_data, 'chessevent_status')
        if not status_id:
            return NeverSyncedChessEventStatus()
        return _ChessEventRequestStatusManager.get_object(status_id)


class _ChessEventRequestStatusManager(EntityManager[ChessEventStatus]):
    """Manager for the ChessEvent statuses that are the result of a request.
    Those statuses are the ones stored in the DB."""

    @staticmethod
    def entity_types() -> list[type[ChessEventStatus]]:
        return [
            SuccessChessEventStatus,
            ConnectionErrorChessEventStatus,
            AuthErrorChessEventStatus,
            UnauthorizedErrorChessEventStatus,
            EventNotFoundChessEventStatus,
            TournamentNotFoundChessEventStatus,
            UnexpectedErrorChessEventStatus,
        ]
