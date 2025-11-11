from typing import TYPE_CHECKING
from plugins.hookspec import hookimpl

if TYPE_CHECKING:
    from data.event import Player


class CoreHooks:
    @hookimpl(hookwrapper=True, trylast=True)
    def player_name_for_board_view(self, player: 'Player', default: str):
        """This hook should always be implemented as a hookwrapper so that it returns a single value.
        The core hook provides a base implementation that returns the default value so that other plugins
        can override it.
        """
        outcome = yield
        outcome.force_result(default)
