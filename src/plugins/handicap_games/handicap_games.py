from operator import attrgetter
from typing import Any, TYPE_CHECKING

from packaging.version import Version

from common.i18n import _
from data.columns.board_table import BoardColumn, BlackRatingColumn, WhiteTitleColumn
from plugins.handicap_games import PLUGIN_NAME
from plugins.handicap_games.handicap_games_entity import (
    WhiteTimeControlColumn,
    BlackTimeControlColumn,
)
from plugins.handicap_games.utils import (
    HandicapGameUtils,
    HandicapGamesTournamentPluginData,
    HandicapGamesTransientPlayerPluginData,
)
from plugins.hookspec import hookimpl
from plugins.utils import (
    Plugin,
    PluginData,
    PluginUtils,
)
from utils.time_control import parse_time_control_trf25
from web.controllers.base_controller import WebContext
from web.utils import ColumnUsage

if TYPE_CHECKING:
    from data.event import Event
    from data.tournament import Tournament
    from data.event import Player
    from database.sqlite.event.event_store import StoredTournament


class HandicapGamesPlugin(Plugin):
    @staticmethod
    def static_id() -> str:
        return PLUGIN_NAME

    @staticmethod
    def static_name() -> str:
        return _('Handicap games')

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

        intial_time, inc = parse_time_control_trf25(time_control_trf25)
        if intial_time == 0 and time_control_handicap_penalty_value:
            errors['handicap_games_penalty_value'] = _(
                'Penalties require a time control with a single period.'
            )

    @hookimpl
    def get_tournament_page_template_context(self) -> dict[str, Any]:
        return {'handicap_game_utils': HandicapGameUtils}

    @hookimpl
    def set_for_round(self, tournament: 'Tournament', round_: int):
        plugin_data = HandicapGameUtils.get_tournament_plugin_data(tournament)
        if not plugin_data.penalty_value:
            return

        for board in tournament.get_round_boards(round_):
            if not board.black_player:
                continue
            strong_player: Player
            weak_player: Player
            strong_player, weak_player = sorted(
                (board.white_player, board.black_player),
                key=attrgetter('rating'),
                reverse=True,
            )
            weak_time = tournament.time_control_initial_time or 0
            rating_diff = strong_player.rating - weak_player.rating
            if not plugin_data.penalty_step:
                penalties = 0
            else:
                penalties = rating_diff // plugin_data.penalty_step
            strong_time = max(
                weak_time - penalties * (plugin_data.penalty_value or 0),
                plugin_data.min_time or 0,
            )
            strong_player.transient_plugin_data[PLUGIN_NAME] = (
                HandicapGamesTransientPlayerPluginData(
                    strong_time, tournament.time_control_increment or 0, penalties > 0
                )
            )

            weak_player.transient_plugin_data[PLUGIN_NAME] = (
                HandicapGamesTransientPlayerPluginData(
                    weak_time, tournament.time_control_increment or 0, False
                )
            )

    # ---------------------------------------------------------------------------------
    # Print / Screens
    # ---------------------------------------------------------------------------------

    @hookimpl
    def alter_print_and_screen_board_columns(
        self,
        usage: ColumnUsage,
        board_columns: list[BoardColumn],
        tournament: 'Tournament',
    ):
        plugin_data = HandicapGameUtils.get_tournament_plugin_data(tournament)
        if not plugin_data.penalty_value:
            return
        PluginUtils.insert_on_isinstance(
            board_columns, WhiteTimeControlColumn(usage), WhiteTitleColumn, False
        )
        PluginUtils.insert_on_isinstance(
            board_columns, BlackTimeControlColumn(usage), BlackRatingColumn
        )
