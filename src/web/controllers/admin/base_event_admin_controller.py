import logging
from typing import Annotated, Any

from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template

from common.exception import PapiWebException
from common.i18n import _
from data.event import Event
from data.loader import EventLoader
from web.controllers.admin.base_admin_controller import (
    AdminWebContext,
    BaseAdminController,
)
from web.messages import Message


class BaseEventAdminWebContext(AdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str | None,
        data: Annotated[
            dict[str, str] | None,
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ):
        super().__init__(request, data=data, admin_tab=None)
        self.admin_event: Event | None = None
        if self.error:
            return
        if event_uniq_id:
            try:
                self.admin_event = EventLoader.get(request=self.request).load_event(
                    event_uniq_id
                )
            except PapiWebException as pwe:
                self._redirect_error(f'Event [{event_uniq_id}] not found: {pwe}')
                return

    def check_admin_tab(self):
        pass

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_event': self.admin_event,
        }

    def get_tournament_options(self) -> dict[str, str]:
        if self.admin_event is None:
            raise RuntimeError('admin_event not defined')
        return {
            self.value_to_form_data(
                tournament.id
            ): f'{tournament.name} ({tournament.uniq_id})'
            for tournament in self.admin_event.tournaments_sorted_by_uniq_id
        }


class BaseEventAdminController(BaseAdminController):
    @classmethod
    def _get_admin_event_render_context(
        cls,
        web_context: BaseEventAdminWebContext,
    ) -> dict[str, Any]:
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        admin_event: Event = web_context.admin_event
        logging_levels: dict[int, dict[str, str]] = {
            logging.DEBUG: {
                'name': 'DEBUG',
                'class': 'bg-secondary-subtle text-secondary-emphasis',
                'icon_class': 'bi-search',
            },
            logging.INFO: {
                'name': 'INFO',
                'class': 'bg-info-subtle text-info-emphasis',
                'icon_class': 'bi-info-circle',
            },
            logging.WARNING: {
                'name': 'WARNING',
                'class': 'bg-warning-subtle text-warning-emphasis',
                'icon_class': 'bi-exclamation-triangle',
            },
            logging.ERROR: {
                'name': 'ERROR',
                'class': 'bg-danger-subtle text-danger-emphasis',
                'icon_class': 'bi-bug',
            },
            logging.CRITICAL: {
                'name': 'CRITICAL',
                'class': 'bg-danger text-white',
                'icon_class': 'bi-sign-stop',
            },
        }
        nav_tabs: dict[str, dict[str, str | dict[str, dict[str, str]]]] = {
            'admin-event-config-tab': {
                'title': admin_event.uniq_id,
                'template': 'event/tab.html',
                'icon_class': 'bi-gear',
            },
            'admin-event-tournaments-tab': {
                'title': _('Tournaments ({num})').format(
                    num=len(admin_event.tournaments_by_id) or '-'
                ),
                'template': 'tournaments/tab.html',
            },
            'admin-event-players-tab': {
                'title': _('Players ({num})').format(
                    num=admin_event.player_count or '-'
                ),
                'template': 'players/tab.html',
            },
            'admin-event-pairings-tab': {
                'title': _('Pairings'),
                'template': 'pairings/tab.html',
            },
            'admin-event-views': {
                'title': _('Screens'),
                'submenu': {
                    'admin-event-screens-tab': {
                        'title': _('Individual Screens ({num})').format(
                            num=len(admin_event.basic_screens_by_id) or '-'
                        ),
                        'template': 'screens/tab.html',
                    },
                    'admin-event-families-tab': {
                        'title': _('Families ({num})').format(
                            num=len(admin_event.families_by_id) or '-'
                        ),
                        'template': 'families/tab.html',
                    },
                    'admin-event-rotators-tab': {
                        'title': _('Rotators ({num})').format(
                            num=len(admin_event.rotators_by_id) or '-'
                        ),
                        'template': 'rotators/tab.html',
                    },
                    'admin-event-timers-tab': {
                        'title': _('Timers ({num})').format(
                            num=len(admin_event.timers_by_id) or '-'
                        ),
                        'template': 'timers/tab.html',
                        'separator': 'true',
                    },
                    'admin-event-client-controllers-tab': {
                        'title': _('Client Controllers ({num})').format(
                            num=len(admin_event.client_controllers_by_id) or '-'
                        ),
                        'template': 'client_controllers/tab.html',
                    },
                },
            },
        }

        template_context: dict[str, Any] = web_context.template_context | {
            'messages': Message.messages(web_context.request),
            'logging_levels': logging_levels,
            'nav_tabs': nav_tabs,
        }

        return template_context

    @classmethod
    def _admin_event_render(
        cls,
        template_context: dict[str, Any],
    ) -> Template:
        if 'modal' in template_context:
            return HTMXTemplate(
                template_name='admin/modals.html',
                context=template_context,
                re_target='#modal-wrapper',
                re_swap='innerHTML',
                trigger_event='modal_opened',
                after='settle',
            )
        return HTMXTemplate(
            template_name='admin/event_layout.html', context=template_context
        )
