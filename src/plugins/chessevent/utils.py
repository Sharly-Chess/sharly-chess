from dataclasses import dataclass
from functools import partial
from typing import Any, Self

from data.event import Event
from data.tournament import Tournament
from plugins.chessevent import PLUGIN_NAME
from plugins.utils import PluginData, PluginUtils
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
from web.controllers.base_controller import WebContext

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class ChessEventUtils:
    @classmethod
    def resolve_user_id(cls, tournament: Tournament) -> str | None:
        tournament_plugin_data = cls.get_tournament_plugin_data(tournament)
        if tournament_plugin_data.user:
            return tournament_plugin_data.user
        event_plugin_data = cls.get_event_plugin_data(tournament.event)
        return event_plugin_data.user

    @classmethod
    def resolve_password(cls, tournament: Tournament) -> str | None:
        tournament_plugin_data = cls.get_tournament_plugin_data(tournament)
        if tournament_plugin_data.password:
            return tournament_plugin_data.password
        event_plugin_data = cls.get_event_plugin_data(tournament.event)
        return event_plugin_data.password

    @classmethod
    def resolve_event_id(cls, tournament: Tournament) -> str | None:
        tournament_plugin_data = cls.get_tournament_plugin_data(tournament)
        if tournament_plugin_data.event_id:
            return tournament_plugin_data.event_id
        event_plugin_data = cls.get_event_plugin_data(tournament.event)
        return event_plugin_data.event_id

    @classmethod
    def resolve_tournament_name(cls, tournament: Tournament) -> str | None:
        tournament_plugin_data = cls.get_tournament_plugin_data(tournament)
        return tournament_plugin_data.tournament_name

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

        tournament_plugin_data = cls.get_tournament_plugin_data(tournament)
        status = tournament_plugin_data.status
        if not status:
            return NeverSyncedChessEventStatus()
        return _ChessEventRequestStatusManager.get_object(status)

    @staticmethod
    def get_event_plugin_data(event: Event) -> 'ChessEventEventPluginData':
        plugin_data = event.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, ChessEventEventPluginData)
        return plugin_data

    @staticmethod
    def get_tournament_plugin_data(
        tournament: Tournament,
    ) -> 'ChessEventTournamentPluginData':
        plugin_data = tournament.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, ChessEventTournamentPluginData)
        return plugin_data


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


@dataclass
class ChessEventEventPluginData(PluginData):
    user: str | None
    password: str | None
    event_id: str | None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            user=stored_value.get('user'),
            password=stored_value.get('password'),
            event_id=stored_value.get('event_id'),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'user': self.user,
            'password': self.password,
            'event_id': self.event_id,
        }

    @classmethod
    def from_form_data(
        cls, data: dict[str, str], previous_object: Self | None = None
    ) -> Self:
        return cls(
            user=WebContext.form_data_to_str(data, 'chessevent_user'),
            password=WebContext.form_data_to_str(data, 'chessevent_password'),
            event_id=WebContext.form_data_to_str(data, 'chessevent_event_id'),
        )

    def to_form_data(self) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'chessevent_user': self.user,
                'chessevent_password': self.password,
                'chessevent_event_id': self.event_id,
            }
        )


@dataclass
class ChessEventTournamentPluginData(PluginData):
    user: str | None
    password: str | None
    event_id: str | None
    tournament_name: str | None
    status: str | None
    last_sync: float | None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            user=stored_value.get('user'),
            password=stored_value.get('password'),
            event_id=stored_value.get('event_id'),
            tournament_name=stored_value.get('tournament_name'),
            status=stored_value.get('status'),
            last_sync=stored_value.get('last_sync', 0.0),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'user': self.user,
            'password': self.password,
            'event_id': self.event_id,
            'tournament_name': self.tournament_name,
            'status': self.status,
            'last_sync': self.last_sync,
        }

    @classmethod
    def from_form_data(
        cls, data: dict[str, str], previous_object: Self | None = None
    ) -> Self:
        return cls(
            user=previous_object.user if previous_object else None,
            password=previous_object.password if previous_object else None,
            event_id=previous_object.event_id if previous_object else None,
            tournament_name=previous_object.tournament_name
            if previous_object
            else None,
            status=previous_object.status if previous_object else None,
            last_sync=previous_object.last_sync if previous_object else None,
        )

    def to_form_data(self) -> dict[str, str]:
        return {}
