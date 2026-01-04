from typing import Any

from litestar import Response, get
from litestar.plugins.htmx import HTMXRequest
from litestar.response import Template, Redirect

from data.access_levels.actions import AuthAction
from data.display_controller import DisplayController
from data.rotator import Rotator
from data.screen import Screen
from data.tournament import Tournament
from plugins.ffe.ffe_event_controller import HTMXTemplate
from utils.enum import ScreenType
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.index_controller import HTTP_204_NO_CONTENT
from web.guards import EventGuard
from web.urls import (
    admin_event_pairings_url,
    admin_event_players_url,
    admin_event_tournaments_url,
)


class EventAdminController(BaseEventAdminController):
    guards = [EventGuard()]

    @classmethod
    def _admin_event_render(
        cls,
        web_context: BaseEventAdminWebContext,
        template_context: dict[str, Any] | None = None,
    ) -> Template:
        return cls._admin_base_event_render(
            web_context.template_context | (template_context or {}),
        )

    @get(
        path='/event/{event_uniq_id:str}',
        name='admin-event',
    )
    async def htmx_admin_event(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | Redirect:
        web_context = BaseEventAdminWebContext(request)
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        if web_context.client.can_view_pairings_tab:
            started_tournaments: list[Tournament] = [
                tournament
                for tournament in web_context.client.allowed_tournaments_for_action(
                    AuthAction.VIEW_PAIRINGS_TAB
                )
                if tournament.started
            ]
            if len(started_tournaments) > 0 and web_context:
                return Redirect(
                    admin_event_pairings_url(
                        request,
                        web_context.admin_event.uniq_id,
                        started_tournaments[0].id,
                    )
                )
        if (
            web_context.admin_event.player_count
            and web_context.client.can_view_players_tab
        ):
            return Redirect(
                admin_event_players_url(request, web_context.admin_event.uniq_id)
            )
        if web_context.client.can_view_tournaments_tab:
            return Redirect(
                admin_event_tournaments_url(request, web_context.admin_event.uniq_id)
            )

        # Search for screens
        if web_context.client.can_view_public_screens:
            screens_by_screen_type_sorted_by_uniq_id: dict[ScreenType, list[Screen]]
            if web_context.client.can_view_private_screens:
                screens_by_screen_type_sorted_by_uniq_id = (
                    web_context.admin_event.screens_by_screen_type_sorted_by_uniq_id
                )
            else:
                screens_by_screen_type_sorted_by_uniq_id = web_context.admin_event.public_screens_by_screen_type_sorted_by_uniq_id
            for screen_type in ScreenType.screen_types():
                if screens_by_screen_type_sorted_by_uniq_id[screen_type]:
                    return Redirect(
                        path=request.app.route_reverse(
                            f'admin-event-{screen_type.value}-screens-tab',
                            event_uniq_id=event_uniq_id,
                        )
                    )
        # Search for rotators
        if web_context.client.can_view_public_screens:
            rotators: list[Rotator]
            if web_context.client.can_view_private_screens:
                rotators = web_context.admin_event.rotators_sorted_by_name
            else:
                rotators = web_context.admin_event.public_rotators_sorted_by_name
            if rotators:
                return Redirect(
                    path=request.app.route_reverse(
                        'admin-event-rotators-tab', event_uniq_id=event_uniq_id
                    )
                )
        # search for display controllers
        if web_context.client.can_view_public_screens:
            display_controllers: list[DisplayController]
            if web_context.client.can_view_private_screens:
                display_controllers = (
                    web_context.admin_event.display_controllers_sorted_by_name
                )
            else:
                display_controllers = (
                    web_context.admin_event.public_display_controllers_sorted_by_name
                )
            if display_controllers:
                return Redirect(
                    path=request.app.route_reverse(
                        'admin-event-displayer_controllers-tab',
                        event_uniq_id=event_uniq_id,
                    )
                )

        # default display with no tab selected
        return self._admin_base_event_render(web_context.template_context)

    @get(
        path='/event/{event_uniq_id:str}/upload-item',
        name='admin-event-upload-item',
    )
    async def htmx_admin_event_upload_item(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> HTMXTemplate | Response:
        web_context = BaseEventAdminWebContext(request)
        upload_item = web_context.template_context['nav_tabs'].get('admin-upload')
        if not upload_item:
            return Response(status_code=HTTP_204_NO_CONTENT, content=None)

        return HTMXTemplate(
            template_name='admin/event_layout_nav_item.html',
            context=web_context.template_context
            | {
                'swap_oob': True,
                'nav_id': 'admin-upload',
                'nav_tab': upload_item,
            },
        )
