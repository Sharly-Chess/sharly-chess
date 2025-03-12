from typing import Any

from litestar import get
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate, ClientRedirect

from data.player import Player
from database.sqlite.fide.fide_database import FideDatabase
from web.controllers.admin.base_event_admin_controller import BaseEventAdminController, BaseEventAdminWebContext


class FideSearchController(BaseEventAdminController):

    @get(
        path='/search/fide/{event_uniq_id:str}',
        name='search-fide',
    )
    async def htmx_search_fide(
            self,
            request: HTMXRequest,
            event_uniq_id: str,
            search_fide: str,
    ) -> Template | ClientRedirect:
        web_context: BaseEventAdminWebContext = BaseEventAdminWebContext(
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
        if search_fide:
            with FideDatabase() as fide_database:
                players: list[Player] = [player for player in fide_database.search_player(search_fide, limit=8)]
        return HTMXTemplate(
            template_name='admin/players/fide_search_results.html',
            context= template_context | {
                'search_results': players,
            },
            push_url=False
        )
