from dataclasses import dataclass
from datetime import datetime
from functools import partial
from logging import Logger
from typing import Any, Self


from common.logger import get_logger
from data.event import Event
from data.player import Player
from data.tournament import Tournament
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.sce import PLUGIN_NAME
from plugins.utils import PluginData, PluginUtils


logger: Logger = get_logger()

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


@dataclass
class SCETokens:
    access_token: str
    refresh_token: str
    expires_at: datetime


@dataclass
class SCEEventPluginData(PluginData):
    id: str | None = None
    tokens: SCETokens | None = None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        tokens: SCETokens | None = None
        if stored_tokens := stored_value.get('tokens'):
            tokens = SCETokens(
                access_token=stored_tokens.get('access_token'),
                refresh_token=stored_tokens.get('refresh_token'),
                expires_at=SQLiteDatabase.load_datetime_from_database_field(
                    stored_tokens.get('expires_at'),
                ),
            )
        return cls(id=stored_value.get('id'), tokens=tokens)

    def to_stored_value(self) -> dict[str, Any]:
        stored_value: dict[str, Any] = {'id': self.id}
        if self.tokens:
            stored_value['tokens'] = {
                'access_token': self.tokens.access_token,
                'refresh_token': self.tokens.refresh_token,
                'expires_at': (
                    SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                        self.tokens.expires_at
                    )
                ),
            }
        return stored_value

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        if previous_object:
            return previous_object
        return cls()

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return {}


@dataclass
class SCETournamentPluginData(PluginData):
    id: str | None = None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            id=stored_value.get('id', None),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'id': self.id,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        return cls(
            id=getattr(previous_object, 'id', None),
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return {}


@dataclass
class SCEPlayerPluginData(PluginData):
    id: str | None = None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            id=stored_value.get('id', None),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'id': self.id,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        return cls(
            id=getattr(previous_object, 'id', None),
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return {}


class SCEUtils:
    @staticmethod
    def get_event_plugin_data(event: Event) -> SCEEventPluginData:
        plugin_data = event.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, SCEEventPluginData)
        return plugin_data

    @staticmethod
    def get_tournament_plugin_data(tournament: Tournament) -> SCETournamentPluginData:
        plugin_data = tournament.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, SCETournamentPluginData)
        return plugin_data

    @staticmethod
    def get_player_plugin_data(player: Player) -> SCEPlayerPluginData:
        plugin_data = player.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, SCEPlayerPluginData)
        return plugin_data
