from typing import Any

from litestar import get
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate, ClientRedirect

from data.player import Player
from database.sqlite.ffe_database import FfeDatabase
from web.controllers.admin.event_admin_controller import AbstractEventAdminController, EventAdminWebContext


class FfeSearchController(AbstractEventAdminController):

    @get(
        path='/search/ffe/{event_uniq_id:str}',
        name='search-ffe',
    )
    async def htmx_search_ffe(
            self,
            request: HTMXRequest,
            event_uniq_id: str,
            search: str,
    ) -> Template | ClientRedirect:
        web_context: EventAdminWebContext = EventAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            admin_event_tab='players',
            data=None,
        )
        if web_context.error:
            return web_context.error
        template_context: dict[str, Any] = self._get_admin_event_render_context(
            web_context
        )
        players: list[Player] | None = None
        if search:
            with FfeDatabase() as ffe_database:
                players: list[Player] = [player for player in ffe_database.search_player(search, limit=8)]
        return HTMXTemplate(
            template_name='admin/players/ffe_search_results.html',
            context= template_context | {
                'search_results': players,
            }
        )
