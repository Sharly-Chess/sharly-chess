from functools import partial
from litestar import get
from litestar.response import Template
from litestar_htmx import HTMXRequest

from data.access_levels.actions import AuthAction
from plugins.fra_schools import PLUGIN_NAME
from plugins.fra_schools.fra_schools_session_handler import FRASchoolsSessionHandler
from plugins.utils import PluginUtils
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
)
from web.controllers.admin.player_admin_controller import PlayerAdminController
from web.guards import EventGuard, ActionGuard
from web.session import SessionHandler

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class FraSchoolsAdminEventController(BaseEventAdminController):
    guards = []

    @get(
        path='/fra-schools/event/{event_uniq_id:str}/players',
        name='fra-schools-admin-event-players-tab',
        guards=[EventGuard(), ActionGuard(AuthAction.VIEW_PLAYERS_TAB)],
    )
    async def htmx_fra_schools_event_tab(
        self,
        request: HTMXRequest,
        fra_schools_filter: list[int] | None = None,
        admin_players_sort: str | None = None,
    ) -> Template:
        if admin_players_sort is not None:
            SessionHandler.set_session_admin_players_sort(request, admin_players_sort)
        if fra_schools_filter is not None:
            FRASchoolsSessionHandler.set_session_filter_schools(
                request,
                [school_id for school_id in fra_schools_filter if school_id != -1],
            )
        PlayerAdminController.set_players_search_results(request)
        return PlayerAdminController._admin_event_players_render(
            request, reload_event=True
        )
