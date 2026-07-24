from datetime import datetime
from typing import TYPE_CHECKING, override

from common.i18n import _
from data.screens.screen_types import ScreenType
from plugins.chess960 import PLUGIN_NAME

if TYPE_CHECKING:
    from data.event import Event
    from data.screens.screen import Screen


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
            'Chess960 screens hold a Chess960 start position that can be displayed to the players.'
        )

    @property
    @override
    def families_allowed(self) -> bool:
        return False

    @override
    def default_screen_name(self, screen: 'Screen') -> str:
        return _('Chess960 start position')

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

    @staticmethod
    def _plugin_data(screen: 'Screen'):
        from plugins.chess960.utils import Chess960ScreenPluginData

        plugin_data = screen.plugin_data.get(PLUGIN_NAME)
        assert isinstance(plugin_data, Chess960ScreenPluginData)
        return plugin_data

    @override
    def create_form_data(self, event: 'Event') -> dict:
        return {
            'columns': 1,
            'chess960_number': '',
        }

    @override
    def default_form_data(self, screen: 'Screen') -> dict:
        return self._plugin_data(screen).to_form_data()

    @override
    def content_context(self, screen: 'Screen') -> dict:
        from plugins.chess960.utils import board_svg

        plugin_data = self._plugin_data(screen)
        return {
            'chess960_number': plugin_data.chess960_number,
            'board_svg': board_svg(plugin_data.chess960_number),
        }

    @override
    def refresh_needed(self, screen: 'Screen', since: datetime) -> bool:
        return screen.last_update > since
