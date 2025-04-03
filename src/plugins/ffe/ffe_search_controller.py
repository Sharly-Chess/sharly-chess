import time
from typing import Any, TYPE_CHECKING

from litestar import get
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate, ClientRedirect

from common import DEVEL_ENV, unicode_normalize
from common.exception import PapiWebException
from common.i18n import ngettext, _
from common.network import NetworkMonitor
from data.util import PlayerRatingType, TournamentRating
from database.sqlite.fide.fide_database import FideDatabase
from plugins.ffe.ffe_database import FfeDatabase
from plugins.ffe.ffe_sql_server import FFESqlServer
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.admin.player_admin_controller import PlayerAdminController

if TYPE_CHECKING:
    from data.player import Player


class FfeSearchController(BaseEventAdminController):
    MAX_RESULTS: int = 10

    @get(
        path='/ffe/search/{event_uniq_id:str}',
        name='ffe-search',
    )
    async def htmx_ffe_search(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        search_ffe: str,
    ) -> Template | ClientRedirect:
        web_context: BaseEventAdminWebContext = BaseEventAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            data=None,
        )
        if web_context.error:
            return web_context.error
        template_context: dict[str, Any] = self._get_admin_event_render_context(
            web_context
        )
        search_results: list['Player'] = []
        search_messages: list[tuple] = []
        if search_ffe:
            start: float = 0.0
            if DEVEL_ENV:
                start = time.perf_counter()
            try:
                async with FFESqlServer() as ffe_sql_server:
                    search_results = [
                        player
                        async for player in await ffe_sql_server.search_player(
                            unicode_normalize(search_ffe), limit=self.MAX_RESULTS
                        )
                    ]
                    if DEVEL_ENV:
                        seconds: float = time.perf_counter() - start
                        if len(search_results):
                            message = ngettext(
                                '{num} player found in {seconds:.2f} seconds.',
                                '{num} players found in {seconds:.2f} seconds.',
                                len(search_results),
                            ).format(num=len(search_results), seconds=seconds)
                        else:
                            message = _(
                                'No players found in {seconds:.2f} seconds.'
                            ).format(seconds=seconds)
                    else:
                        if len(search_results):
                            message = ngettext(
                                '{num} player found.',
                                '{num} players found.',
                                len(search_results),
                            ).format(num=len(search_results))
                        else:
                            message = _('No players found.')
                    search_messages.append(
                        (
                            'bi-cloud-arrow-down-fill',
                            'text-primary',
                            message,
                        )
                    )
            except PapiWebException as e:
                search_messages.append(('bi-cloud-slash', '', str(e)))
                start = 0.0
                if DEVEL_ENV:
                    start = time.perf_counter()
                if not FfeDatabase().exists():
                    search_messages.append(
                        ('bi-database-slash', '', _('No local database.'))
                    )
                else:
                    with FfeDatabase() as ffe_database:
                        search_results = [
                            player
                            for player in ffe_database.search_player(
                                unicode_normalize(search_ffe), limit=self.MAX_RESULTS
                            )
                        ]
                        if DEVEL_ENV:
                            seconds = time.perf_counter() - start
                            if len(search_results):
                                message = ngettext(
                                    '{num} player found in {seconds:.2f} seconds.',
                                    '{num} players found in {seconds:.2f} seconds.',
                                    len(search_results),
                                ).format(num=len(search_results), seconds=seconds)
                            else:
                                message = _(
                                    'No players found in {seconds:.2f} seconds.'
                                ).format(seconds=seconds)
                        else:
                            if len(search_results):
                                message = ngettext(
                                    '{num} player found.',
                                    '{num} players found.',
                                    len(search_results),
                                ).format(num=len(search_results))
                            else:
                                message = _('No players found.')
                        search_messages.append(
                            (
                                'bi-database-fill-check',
                                'text-primary',
                                message,
                            )
                        )
        return HTMXTemplate(
            template_name='/ffe_search_results.html',
            context=template_context
            | {
                'search_results': search_results,
                'search_messages': search_messages,
            },
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
        ffe_player: Player | None = None
        if player_ffe_id:
            if NetworkMonitor.connected():
                async with FFESqlServer() as ffe_sql_server:
                    ffe_player: Player = await ffe_sql_server.get_player_by_ffe_id(
                        player_ffe_id
                    )
            elif (ffe_database := FfeDatabase()).exists():
                with ffe_database:
                    ffe_player: Player = ffe_database.get_player_by_ffe_id(
                        player_ffe_id
                    )

            # Try to get more information by requesting the FIDE database
            if (
                ffe_player
                and ffe_player.fide_id
                and (fide_database := FideDatabase()).exists()
            ):
                with fide_database:
                    if fide_player := fide_database.get_player_by_fide_id(
                        ffe_player.fide_id
                    ):
                        ffe_player.federation = fide_player.federation
                        ffe_player.title = fide_player.title
                        for rating_type in [
                            TournamentRating.STANDARD,
                            TournamentRating.RAPID,
                            TournamentRating.BLITZ,
                        ]:
                            if (
                                ffe_player.rating_types[rating_type]
                                == PlayerRatingType.ESTIMATED
                                and fide_player.rating_types[rating_type]
                                != PlayerRatingType.ESTIMATED
                            ):
                                ffe_player.ratings[rating_type] = fide_player.ratings[
                                    rating_type
                                ]
                                ffe_player.rating_types[rating_type] = (
                                    fide_player.rating_types[rating_type]
                                )

        return PlayerAdminController._admin_event_players_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='player',
            action='create',
            player_from_plugin=ffe_player,
        )
