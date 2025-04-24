from litestar import get
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate, Reswap, ClientRedirect
from litestar.response import Template
from litestar.status_codes import HTTP_304_NOT_MODIFIED

from common.i18n import _
from data.event import Event
from data.loader import EventLoader
from web.controllers.user.base_user_controller import BaseUserController, UserWebContext
from web.messages import Message


class IndexUserController(BaseUserController):
    @staticmethod
    def _user_render(
        web_context: UserWebContext,
    ) -> Template | ClientRedirect:
        event_loader: EventLoader = EventLoader.get(request=web_context.request)
        current_events: list[Event]
        coming_events: list[Event]
        passed_events: list[Event]
        if web_context.admin_auth:
            current_events = event_loader.current_events
            coming_events = event_loader.coming_events
            passed_events = event_loader.passed_events
        else:
            current_events = event_loader.current_public_events
            coming_events = event_loader.coming_public_events
            passed_events = event_loader.passed_public_events
        nav_tabs: dict[str, dict] = {
            'current_events': {
                'title': _('Current events ({num})').format(
                    num=len(current_events) or '-'
                ),
                'events': current_events,
                'empty_str': _('No current events.'),
                'class': 'bg-primary-subtle',
                'icon_class': 'bi-calendar',
                'disabled': not current_events,
            },
            'coming_events': {
                'title': _('Upcoming events ({num})').format(
                    num=len(coming_events) or '-'
                ),
                'events': coming_events,
                'empty_str': _('No upcoming events.'),
                'class': 'bg-info-subtle',
                'icon_class': 'bi-calendar-check',
                'disabled': not coming_events,
            },
            'passed_events': {
                'title': _('Passed events ({num})').format(
                    num=len(passed_events) or '-'
                ),
                'events': passed_events,
                'empty_str': _('No passed events.'),
                'class': 'bg-secondary-subtle',
                'icon_class': 'bi-calendar-minus',
                'disabled': not passed_events,
            },
        }
        if not web_context.user_tab or nav_tabs[web_context.user_tab]['disabled']:
            web_context.user_tab = list(nav_tabs.keys())[0]
        for nav_index in range(len(nav_tabs)):
            if (
                web_context.user_tab == list(nav_tabs.keys())[nav_index]
                and nav_tabs[web_context.user_tab]['disabled']
            ):
                web_context.user_tab = list(nav_tabs.keys())[
                    (nav_index + 1) % len(nav_tabs)
                ]
        return HTMXTemplate(
            template_name='user/index.html',
            context=web_context.template_context
            | {
                'messages': Message.messages(web_context.request),
                'nav_tabs': nav_tabs,
            },
        )

    @staticmethod
    def _user_refresh_needed(
        web_context: UserWebContext,
        date: float,
    ) -> bool:
        event_loader: EventLoader = EventLoader.get(request=web_context.request)
        events: list[Event]
        if web_context.admin_auth:
            events = list(event_loader.events_by_id.values())
        else:
            events = event_loader.public_events
        for event in events:
            if event.last_update and event.last_update > date:
                return True
            for tournament in event.tournaments_by_id.values():
                if tournament.last_update > date:
                    return True
        return False

    def _user(
        self,
        request: HTMXRequest,
        user_tab: str | None,
        locale: str | None,
    ) -> Template | Reswap | ClientRedirect:
        self.set_locale(request, locale)
        web_context: UserWebContext = UserWebContext(
            request, data=None, user_tab=user_tab
        )
        if web_context.error:
            return web_context.error
        date: float | None = self.get_if_modified_since(request)
        if date is None or self._user_refresh_needed(web_context, date):
            return self._user_render(web_context)
        else:
            return Reswap(
                content=None, method='none', status_code=HTTP_304_NOT_MODIFIED
            )

    @get(
        path='/user',
        name='user',
    )
    async def htmx_user(
        self,
        request: HTMXRequest,
        locale: str | None,
    ) -> Template | Reswap | ClientRedirect:
        return self._user(request, user_tab=None, locale=locale)

    @get(
        path='/user/{user_tab:str}',
        name='user-tab',
    )
    async def htmx_user_tab(
        self,
        request: HTMXRequest,
        user_tab: str,
        locale: str | None,
    ) -> Template | Reswap | ClientRedirect:
        return self._user(request, user_tab=user_tab, locale=locale)
