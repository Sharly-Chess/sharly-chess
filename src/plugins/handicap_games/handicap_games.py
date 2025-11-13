from operator import attrgetter
from typing import Any, TYPE_CHECKING

from packaging.version import Version

from plugins.handicap_games import _, PLUGIN_NAME
from plugins.handicap_games.utils import (
    HandicapGameUtils,
    HandicapGamesTournamentPluginData,
    HandicapGamesTransientPlayerPluginData,
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
    # Players
    # ---------------------------------------------------------------------------------

    @hookimpl(hookwrapper=True)
    def player_name_for_board_view(self, player: 'Player', default: str):
        outcome = yield
        try:
            result = outcome.get_result()
        except BaseException as e:
            outcome.force_exception(e)
            return

        plugin_data = HandicapGameUtils.get_tournament_plugin_data(player.tournament)
        if not plugin_data.penalty_value:
            return result

        transient_data = HandicapGameUtils.get_transient_player_plugin_data(player)
        time_control_initial_time_minutes = (
            transient_data.initial_time // 60 if transient_data.initial_time else None
        )
        time_control_initial_time_seconds = (
            transient_data.initial_time % 60 if transient_data.initial_time else None
        )

        cls = (
            'time-control-modified'
            if transient_data.modified
            else 'time-control-unchanged'
        )
        inner = ''

        if time_control_initial_time_minutes:
            inner += (
                f'<span class="minutes">{time_control_initial_time_minutes}\'</span>'
            )

        if time_control_initial_time_seconds:
            inner += (
                f'<span class="seconds">{time_control_initial_time_seconds}"</span>'
            )

        if player.tournament.time_control_increment:
            inner += f' + {player.tournament.time_control_increment}"{_("/move")}'

        outcome.force_result(f'{result} (<span class="{cls}">{inner}</span>)')

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
