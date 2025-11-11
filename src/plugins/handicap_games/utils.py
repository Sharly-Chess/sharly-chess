from dataclasses import dataclass
from functools import partial
from logging import Logger
from typing import Any, Self


from common.logger import get_logger
from data.event import Player
from data.tournament import Tournament
from plugins.handicap_games import PLUGIN_NAME
from plugins.utils import PluginData, PluginUtils
from web.controllers.base_controller import WebContext


logger: Logger = get_logger()

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class HandicapGameUtils:
    @staticmethod
    def get_tournament_plugin_data(
        tournament: Tournament,
    ) -> 'HandicapGamesTournamentPluginData':
        plugin_data = tournament.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, HandicapGamesTournamentPluginData)
        return plugin_data

    @staticmethod
    def get_transient_player_plugin_data(
        player: Player,
    ) -> 'HandicapGamesTransientPlayerPluginData':
        plugin_data = player.transient_plugin_data.get(
            PLUGIN_NAME, HandicapGamesTransientPlayerPluginData()
        )
        assert isinstance(plugin_data, HandicapGamesTransientPlayerPluginData)
        return plugin_data


@dataclass
class HandicapGamesTournamentPluginData(PluginData):
    penalty_step: int | None = None
    penalty_value: int | None = None
    min_time: int | None = None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            penalty_step=stored_value.get('penalty_step', None),
            penalty_value=stored_value.get('penalty_value', None),
            min_time=stored_value.get('min_time', None),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'penalty_step': self.penalty_step,
            'penalty_value': self.penalty_value,
            'min_time': self.min_time,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        return cls(
            penalty_step=WebContext.form_data_to_int(
                data, 'handicap_games_penalty_step'
            ),
            penalty_value=WebContext.form_data_to_int(
                data, 'handicap_games_penalty_value'
            ),
            min_time=WebContext.form_data_to_int(data, 'handicap_games_min_time'),
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'handicap_games_penalty_step': self.penalty_step,
                'handicap_games_penalty_value': self.penalty_value,
                'handicap_games_min_time': self.min_time,
            }
        )


@dataclass
class HandicapGamesTransientPlayerPluginData:
    initial_time: int | None = None
    increment: int | None = None
    modified: bool = False
