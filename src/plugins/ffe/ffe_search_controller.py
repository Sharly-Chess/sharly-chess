from typing import Any, TYPE_CHECKING

from data.util import PlayerRatingType, TournamentRating
from database.sqlite.fide.fide_database import FideDatabase
from litestar import get
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate, ClientRedirect

from plugins.ffe.ffe_database import FfeDatabase
from web.controllers.admin.base_event_admin_controller import BaseEventAdminController, BaseEventAdminWebContext
from web.controllers.admin.player_admin_controller import PlayerAdminController

if TYPE_CHECKING:
    from data.player import Player
    
class FfeSearchController(BaseEventAdminController):

    @get(
        path='/ffe/search/{event_uniq_id:str}',
        name='ffe-search',
    )
    async def htmx_search_ffe(
            self,
            request: HTMXRequest,
            event_uniq_id: str,
            search_ffe: str,
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
        players: list['Player'] | None = None
        if search_ffe:
            with FfeDatabase() as ffe_database:
                players: list['Player'] = [player for player in ffe_database.search_player(search_ffe, limit=8)]
        return HTMXTemplate(
            template_name='/ffe_search_results.html',
            context= template_context | {
                'search_results': players,
            }
        )
        
    @get(
        path='/ffe/create-from-ffe/{event_uniq_id:str}/{player_ffe_id:int}',
        name='ffe-create-from-modal',
        cache=1,
    )
    async def htmx_admin_player_create_from_ffe_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        player_ffe_id: int | None,
    ) -> Template | ClientRedirect:
        if player_ffe_id:
            with FfeDatabase() as ffe_database:
                player = ffe_database.get_player_by_ffe_id(player_ffe_id)
                # Try to get more information by requesting the FIDE database
                with FideDatabase() as fide_database:
                    if fide_player := fide_database.get_player_by_fide_id(player.fide_id):
                        player.federation = fide_player.federation
                        player.title = fide_player.title
                        for rating_type in [
                            TournamentRating.STANDARD,
                            TournamentRating.RAPID,
                            TournamentRating.BLITZ,
                        ]:
                            if player.rating_types[rating_type] == PlayerRatingType.ESTIMATED and fide_player.rating_types[rating_type] != PlayerRatingType.ESTIMATED:
                                player.ratings[rating_type] = fide_player.ratings[rating_type]
                                player.rating_types[rating_type] = fide_player.rating_types[rating_type]
                                    
        return PlayerAdminController._admin_event_players_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='player',
            action='create',
            player_from_plugin=player,
        )