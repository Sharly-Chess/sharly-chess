from datetime import datetime
from typing import TYPE_CHECKING, override

from common.i18n import _
from data.screen_types import ScreenType
from plugins.chess960 import PLUGIN_NAME

if TYPE_CHECKING:
    from data.event import Event
    from data.screen import Screen


class Chess960ScreenType(ScreenType):
    @staticmethod
    def static_id() -> str:
        return 'chess960'

    @staticmethod
    def static_name() -> str:
        return _('Chess960 start position')

    @property
    def icon_str(self) -> str:
        return 'bi-grid-3x3'

    @property
    def tooltip_text(self) -> str:
        return _(
            'Chess960 screens show the start position of the current round '
            'for each tournament.'
        )

    @property
    @override
    def families_allowed(self) -> bool:
        return False

    @property
    @override
    def shows_copyright(self) -> bool:
        return False

    @property
    @override
    def content_template(self) -> str | None:
        return '/chess960_content.html'

    @property
    @override
    def form_template(self) -> str | None:
        return '/chess960_screen_form.html'

    @property
    @override
    def card_action_button_template(self) -> str | None:
        return '/chess960_card_button.html'

    @staticmethod
    def _plugin_data(screen: 'Screen'):
        from plugins.chess960.utils import Chess960ScreenPluginData

        plugin_data = screen.plugin_data.get(PLUGIN_NAME)
        assert isinstance(plugin_data, Chess960ScreenPluginData)
        return plugin_data

    @override
    def create_form_data(self, event: 'Event') -> dict:
        return {'columns': 1, 'show_all_rounds': '', 'fit_to_screen': 'true'}

    @override
    def default_form_data(self, screen: 'Screen') -> dict:
        return self._plugin_data(screen).to_form_data()

    @override
    def content_context(self, screen: 'Screen') -> dict:
        from plugins.chess960.utils import board_svg

        plugin_data = self._plugin_data(screen)
        cells: list[dict] = []
        for chess960_set in plugin_data.sets:
            tournament = screen.event.tournaments_by_id.get(chess960_set.tournament_id)
            if tournament is None:
                continue
            if plugin_data.show_all_rounds:
                rounds = list(range(1, tournament.rounds + 1))
            elif tournament.current_round:
                rounds = [tournament.current_round]
            else:
                rounds = []
            for round_ in rounds:
                number = chess960_set.position_for_round(round_)
                cells.append(
                    {
                        'tournament_name': tournament.name,
                        'round': round_,
                        'number': number,
                        'board_svg': board_svg(number),
                    }
                )
        return {
            'title': screen.name,
            'cells': cells,
            'columns': screen.columns or 1,
            'fit_to_screen': plugin_data.fit_to_screen,
        }

    @override
    def refresh_needed(self, screen: 'Screen', since: datetime) -> bool:
        return any(
            max(tournament.last_update, tournament.last_pairing_update) > since
            for tournament in screen.event.tournaments
        )
