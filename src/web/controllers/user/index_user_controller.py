from litestar import get
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate, Reswap, ClientRedirect
from litestar.response import Template
from litestar.status_codes import HTTP_304_NOT_MODIFIED

from common import format_timestamp_time, format_timestamp_date
from common.i18n import _
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from web.controllers.user.base_user_controller import BaseUserController, UserWebContext
from web.messages import Message


class IndexUserController(BaseUserController):
    @staticmethod
    def _user_render(
        web_context: UserWebContext,
    ) -> Template | ClientRedirect:
        public_only = not web_context.admin_auth
        passed_events = EventLoader.get_events_metadata('passed', public_only)
        current_events = EventLoader.get_events_metadata('current', public_only)
        coming_events = EventLoader.get_events_metadata('coming', public_only)
        nav_tabs: dict[str, dict] = {
            'current_events': {
                'title': _('Current events ({num})').format(
                    num=len(current_events) or '-'
                ),
                'events': current_events,
                'admin_empty_str': _('No current events.'),
                'empty_str': _(
                    'No current events (only public events are displayed on clients).'
                ),
                'class': 'bg-primary-subtle',
                'icon_class': 'bi-calendar',
                'disabled': not current_events,
            },
            'coming_events': {
                'title': _('Upcoming events ({num})').format(
                    num=len(coming_events) or '-'
                ),
                'events': coming_events,
                'admin_empty_str': _('No upcoming events.'),
                'empty_str': _(
                    'No upcoming events (only public events are displayed on clients).'
                ),
                'class': 'bg-info-subtle',
                'icon_class': 'bi-calendar-check',
                'disabled': not coming_events,
            },
            'passed_events': {
                'title': _('Passed events ({num})').format(
                    num=len(passed_events) or '-'
                ),
                'events': passed_events,
                'admin_empty_str': _('No passed events.'),
                'empty_str': _(
                    'No passed events (only public events are displayed on clients).'
                ),
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
                'format_timestamp_date': format_timestamp_date,
                'format_timestamp_time': format_timestamp_time,
            },
        )

    @staticmethod
    def _user_refresh_needed(
        web_context: UserWebContext,
        date: float,
    ) -> bool:
        events_metadata = EventLoader.get_events_metadata(
            public_only=not web_context.admin_auth
        )
        return any(
            EventDatabase(event.uniq_id).file_modified_at > date
            for event in events_metadata
        )

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
