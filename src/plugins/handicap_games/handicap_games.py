from typing import Any, TYPE_CHECKING

from packaging.version import Version

from common.i18n import _
from plugins.handicap_games import PLUGIN_NAME
from plugins.handicap_games.utils import (
    HandicapGameUtils,
    HandicapGamesTournamentPluginData,
)
from plugins.hookspec import hookimpl
from plugins.utils import (
    Plugin,
    PluginData,
)

from utils.time_control import parse_time_control_trf25
from web.controllers.base_controller import WebContext

if TYPE_CHECKING:
    from data.event import Event
    from data.tournament import Tournament
    from database.sqlite.event.event_store import StoredTournament


class HandicapGamesPlugin(Plugin):
    @staticmethod
    def static_id() -> str:
        return PLUGIN_NAME

    @staticmethod
    def static_name() -> str:
        return _('Handicap Games')

    @property
    def description(self) -> str:
        return _(
            'Adds features for handicap tournaments where weaker players are given a time advantage.'
        )

    @property
    def version(self) -> Version:
        return Version('1.0.0')

    @property
    def default_is_enabled(self) -> bool:
        return False

    @property
    def default_event_is_enabled(self) -> bool:
        return False

    def used_by_stored_tournament(self, stored_tournament: 'StoredTournament') -> bool:
        handicap_games_data = stored_tournament.plugin_data.get(PLUGIN_NAME, {})
        if any(
            handicap_games_data.get(k)
            for k in ('penalty_step', 'penalty_value', 'min_time')
        ):
            return True
        return False

    # ---------------------------------------------------------------------------------
    # Tournaments
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_tournament_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        return self.id, HandicapGamesTournamentPluginData

    @hookimpl
    def get_tournament_form_fields_template_and_data(
        self, event: 'Event', tournament: 'Tournament | None'
    ) -> tuple[str, dict[str, Any]]:
        return (
            '/handicap_games_tournament_form_fields.html',
            {},
        )

    @hookimpl
    def validate_tournament_form_fields(
        self,
        action: str,
        tournament: 'Tournament | None',
        data: dict[str, str],
        errors: dict[str, str],
    ):
        time_control_trf25 = WebContext.form_data_to_str(data, 'time_control_trf25')
        time_control_handicap_penalty_value = WebContext.form_data_to_int(
            data, 'handicap_games_penalty_value'
        )

        if time_control_trf25:
            intial_time, inc = parse_time_control_trf25(time_control_trf25)
            if intial_time == 0 and time_control_handicap_penalty_value:
                errors['handicap_games_penalty_value'] = _(
                    'Penalties require a time control with a single period.'
                )

    @hookimpl
    def get_tournament_page_template_context(self) -> dict[str, Any]:
        return {'handicap_game_utils': HandicapGameUtils}
