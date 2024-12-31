import logging
from logging import Logger
from typing import Annotated, Any

from litestar import get, patch, delete, post
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import HTMXTemplate, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, Redirect
from litestar.status_codes import HTTP_200_OK

from common.exception import PapiWebException
from common.i18n import _
from common.logger import get_logger
from common.papi_web_config import PapiWebConfig
from data.event import Event
from data.loader import EventLoader
from database.sqlite import EventDatabase
from database.store import StoredEvent
from web.controllers.admin.index_admin_controller import AdminWebContext, AbstractIndexAdminController
from web.controllers.index_controller import AbstractController
from web.messages import Message
from web.session import SessionHandler

logger: Logger = get_logger()


class EventAdminWebContext(AdminWebContext):
    def __init__(
            self, request: HTMXRequest,
            event_uniq_id: str | None,
            admin_event_tab: str | None,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ] | None,
    ):
        super().__init__(request, data=data, admin_tab=None)
        self.admin_event: Event | None = None
        self.admin_event_tab: str | None = admin_event_tab
        if self.error:
            return
        if event_uniq_id:
            try:
                self.admin_event = EventLoader.get(request=self.request).load_event(event_uniq_id)
            except PapiWebException as pwe:
                self._redirect_error(f'Event [{event_uniq_id}] not found: {pwe}')
                return

    def check_admin_tab(self):
        pass

    @property
    def background_image(self) -> str:
        if self.admin_event:
            return self.admin_event.background_image
        else:
            return super().background_image

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_event_tab': self.admin_event_tab,
            'admin_event': self.admin_event,
        }

    def get_tournament_options(self) -> dict[str, str]:
        options: dict[str, str] = {
        }
        for tournament in self.admin_event.tournaments_by_id.values():
            options[str(tournament.id)] = f'{tournament.name} ({tournament.filename})'
        return options


class AbstractEventAdminController(AbstractIndexAdminController):

    @classmethod
    def _get_admin_event_render_context(
            cls,
            web_context: EventAdminWebContext,
    ) -> dict[str, Any]:
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
                'icon_class': 'bi-bug-fill',
            },
            logging.CRITICAL: {
                'name': 'CRITICAL',
                'class': 'bg-danger text-white',
                'icon_class': 'bi-sign-stop-fill',
            },
        }
        nav_tabs: dict[str, dict[str, str]] = {
            'config': {
                'title': web_context.admin_event.uniq_id,
                'template': 'admin_event_config.html',
                'icon_class': 'bi-gear-fill',
            },
            'tournaments': {
                'title': _('Tournaments ({num})').format(num=len(web_context.admin_event.tournaments_by_id) or '-'),
                'template': 'admin_tournaments.html',
            },
            'screens': {
                'title': _('Screens ({num})').format(num=len(web_context.admin_event.basic_screens_by_id) or '-'),
                'template': 'admin_screens.html',
            },
            'families': {
                'title': _('Families ({num})').format(num=len(web_context.admin_event.families_by_id) or '-'),
                'template': 'admin_families.html',
            },
            'rotators': {
                'title': _('Rotators ({num})').format(num=len(web_context.admin_event.rotators_by_id) or '-'),
                'template': 'admin_rotators.html',
            },
            'timers': {
                'title': _('Timers ({num})').format(num=len(web_context.admin_event.timers_by_id) or '-'),
                'template': 'admin_timers.html',
            },
            'chessevents': {
                'title': _('ChessEvent ({num})').format(num=len(web_context.admin_event.chessevents_by_id) or '-'),
                'template': 'admin_chessevents.html',
            },
            'messages': {
                'title': _('Messages ({num})').format(num=len(web_context.admin_event.messages) or '-'),
                'template': 'admin_messages.html',
            },
        }
        if not web_context.admin_event_tab:
            web_context.admin_event_tab = list(nav_tabs.keys())[0]
        if web_context.admin_event.criticals:
            nav_tabs['messages']['class'] = logging_levels[logging.CRITICAL]['class']
            nav_tabs['messages']['icon_class'] = logging_levels[logging.CRITICAL]['icon_class']
        elif web_context.admin_event.errors:
            nav_tabs['messages']['class'] = logging_levels[logging.ERROR]['class']
            nav_tabs['messages']['icon_class'] = logging_levels[logging.ERROR]['icon_class']
        elif web_context.admin_event.warnings:
            nav_tabs['messages']['class'] = logging_levels[logging.WARNING]['class']
            nav_tabs['messages']['icon_class'] = logging_levels[logging.WARNING]['icon_class']
        return web_context.template_context | {
            'messages': Message.messages(web_context.request),
            'logging_levels': logging_levels,
            'nav_tabs': nav_tabs,
            'admin_columns': SessionHandler.get_session_admin_columns(web_context.request),
            'show_family_screens_on_screen_list': SessionHandler.get_session_show_family_screens_on_screen_list(
                web_context.request),
            'show_details_on_screen_list': SessionHandler.get_session_show_details_on_screen_list(
                web_context.request),
            'show_details_on_family_list': SessionHandler.get_session_show_details_on_family_list(
                web_context.request),
            'show_details_on_rotator_list': SessionHandler.get_session_show_details_on_rotator_list(
                web_context.request),
            'screen_types_on_screen_list': SessionHandler.get_session_screen_types_on_screen_list(
                web_context.request),
            'min_logging_level': SessionHandler.get_session_min_logging_level(web_context.request),
        }

    @classmethod
    def _admin_event_render(
            cls,
            template_context: dict[str, Any],
    ) -> Template:
        return HTMXTemplate(
            template_name="admin_event.html",
            context=template_context)


class EventAdminController(AbstractEventAdminController):

    @classmethod
    def _admin_event_config_render(
            cls,
            request: HTMXRequest,
            event_uniq_id: str,
            admin_event_tab: str | None = None,
            modal: str | None = None,
            action: str | None = None,
            data: dict[str, str] | None = None,
            errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: EventAdminWebContext = EventAdminWebContext(
            request, event_uniq_id=event_uniq_id, admin_event_tab=admin_event_tab, data=data)
        if web_context.error:
            return web_context.error
        template_context: dict[str, Any] = cls._get_admin_event_render_context(web_context)
        match modal:
            case None:
                pass
            case 'event':
                if data is None:
                    data = cls._prepare_event_modal_data(action, request, web_context.admin_event)
                    stored_event: StoredEvent = cls._admin_validate_event_update_data(
                        action, request, web_context.admin_event, data)
                    errors = stored_event.errors
                if errors is None:
                    errors = {}
                template_context |= {
                    'record_illegal_moves_options': cls._get_record_illegal_moves_options(
                        PapiWebConfig.default_record_illegal_moves_number),
                    'timer_color_texts': cls._get_timer_color_texts(PapiWebConfig.default_timer_delays),
                    'background_images_jstree_data': cls.background_images_jstree_data(
                        data['background_image']) if action in ['update', 'clone', ] else {},
                    'modal': 'event',
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case _:
                raise ValueError(f'modal=[{modal}]')
        return cls._admin_event_render(template_context)

    def _admin_event(
            self, request: HTMXRequest,
            event_uniq_id: str,
            admin_event_tab: str | None = None,
            admin_columns: int | None = None,
            locale: str | None = None,
            show_family_screens_on_screen_list: bool | None = None,
            show_details_on_screen_list: bool | None = None,
            show_details_on_family_list: bool | None = None,
            show_details_on_rotator_list: bool | None = None,
            show_boards_screens_on_screen_list: bool | None = None,
            show_input_screens_on_screen_list: bool | None = None,
            show_players_screens_on_screen_list: bool | None = None,
            show_results_screens_on_screen_list: bool | None = None,
            show_image_screens_on_screen_list: bool | None = None,
            min_logging_level: int | None = None,
            modal: str | None = None,
            action: str | None = None,
            data: dict[str, str] | None = None,
            errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        self.set_locale(request, locale)
        self.set_admin_columns(request, admin_columns)
        if show_family_screens_on_screen_list is not None:
            SessionHandler.set_session_show_family_screens_on_screen_list(request, show_family_screens_on_screen_list)
        if show_details_on_screen_list is not None:
            SessionHandler.set_session_show_details_on_screen_list(request, show_details_on_screen_list)
        if show_details_on_family_list is not None:
            SessionHandler.set_session_show_details_on_family_list(request, show_details_on_family_list)
        if show_details_on_rotator_list is not None:
            SessionHandler.set_session_show_details_on_rotator_list(request, show_details_on_rotator_list)
        screen_types: list[str] = SessionHandler.get_session_screen_types_on_screen_list(request)
        for screen_type, param in {
            'boards': show_boards_screens_on_screen_list,
            'input': show_input_screens_on_screen_list,
            'players': show_players_screens_on_screen_list,
            'results': show_results_screens_on_screen_list,
            'image': show_image_screens_on_screen_list,
        }.items():
            if param is not None:
                if param:
                    screen_types.append(screen_type)
                else:
                    screen_types.remove(screen_type)
                SessionHandler.set_session_screen_types_on_screen_list(request, screen_types)
                continue
        if min_logging_level is not None:
            try:
                SessionHandler.set_session_min_logging_level(request, min_logging_level)
            except ValueError:
                return AbstractController.redirect_error(
                    request, f'Invalid log level [{min_logging_level}].')
        return self._admin_event_config_render(
            request, admin_event_tab=admin_event_tab, event_uniq_id=event_uniq_id, modal=modal, action=action,
            data=data, errors=errors)

    @get(
        path='/admin/event/{event_uniq_id:str}',
        name='admin-event',
        cache=1,
    )
    async def htmx_admin_event(
            self, request: HTMXRequest,
            event_uniq_id: str,
            admin_columns: int | None,
            locale: str | None,
            show_family_screens_on_screen_list: bool | None,
            show_details_on_screen_list: bool | None,
            show_details_on_family_list: bool | None,
            show_details_on_rotator_list: bool | None,
            show_boards_screens_on_screen_list: bool | None,
            show_input_screens_on_screen_list: bool | None,
            show_players_screens_on_screen_list: bool | None,
            show_results_screens_on_screen_list: bool | None,
            show_image_screens_on_screen_list: bool | None,
            min_logging_level: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event(
            request,
            event_uniq_id=event_uniq_id,
            admin_event_tab=None,
            admin_columns=admin_columns,
            locale=locale,
            show_family_screens_on_screen_list=show_family_screens_on_screen_list,
            show_details_on_screen_list=show_details_on_screen_list,
            show_details_on_family_list=show_details_on_family_list,
            show_details_on_rotator_list=show_details_on_rotator_list,
            show_boards_screens_on_screen_list=show_boards_screens_on_screen_list,
            show_input_screens_on_screen_list=show_input_screens_on_screen_list,
            show_players_screens_on_screen_list=show_players_screens_on_screen_list,
            show_results_screens_on_screen_list=show_results_screens_on_screen_list,
            show_image_screens_on_screen_list=show_image_screens_on_screen_list,
            min_logging_level=min_logging_level,
        )

    @get(
        path='/admin/event/{event_uniq_id:str}/{admin_event_tab:str}',
        name='admin-event-tab',
        cache=1,
    )
    async def htmx_admin_event_tab(
            self, request: HTMXRequest,
            event_uniq_id: str,
            admin_event_tab: str,
            admin_columns: int | None,
            locale: str | None,
            show_family_screens_on_screen_list: bool | None,
            show_details_on_screen_list: bool | None,
            show_details_on_family_list: bool | None,
            show_details_on_rotator_list: bool | None,
            show_boards_screens_on_screen_list: bool | None,
            show_input_screens_on_screen_list: bool | None,
            show_players_screens_on_screen_list: bool | None,
            show_results_screens_on_screen_list: bool | None,
            show_image_screens_on_screen_list: bool | None,
            min_logging_level: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event(
            request,
            event_uniq_id=event_uniq_id,
            admin_event_tab=admin_event_tab,
            admin_columns=admin_columns,
            locale=locale,
            show_family_screens_on_screen_list=show_family_screens_on_screen_list,
            show_details_on_screen_list=show_details_on_screen_list,
            show_details_on_family_list=show_details_on_family_list,
            show_details_on_rotator_list=show_details_on_rotator_list,
            show_boards_screens_on_screen_list=show_boards_screens_on_screen_list,
            show_input_screens_on_screen_list=show_input_screens_on_screen_list,
            show_players_screens_on_screen_list=show_players_screens_on_screen_list,
            show_results_screens_on_screen_list=show_results_screens_on_screen_list,
            show_image_screens_on_screen_list=show_image_screens_on_screen_list,
            min_logging_level=min_logging_level,
        )

    @get(
        path='/admin/event-modal/{action:str}/{event_uniq_id:str}',
        name='admin-event-modal',
        cache=1,
    )
    async def htmx_admin_event_modal(
            self, request: HTMXRequest,
            action: str,
            event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event(request, modal='event', action=action, event_uniq_id=event_uniq_id, )

    def _admin_event_update(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            action: str,
            event_uniq_id: str | None,
    ) -> Template | ClientRedirect | Redirect:
        match action:
            case 'clone' | 'update' | 'delete':
                web_context: EventAdminWebContext = EventAdminWebContext(
                    request, event_uniq_id=event_uniq_id, admin_event_tab=None, data=data)
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        stored_event: StoredEvent = self._admin_validate_event_update_data(
            action, request, web_context.admin_event, data)
        if stored_event.errors:
            return self._admin_event_config_render(
                request, event_uniq_id=event_uniq_id, modal='event', action=action, data=data,
                errors=stored_event.errors)
        uniq_id: str = stored_event.uniq_id
        event_loader = EventLoader.get(request=request)
        match action:
            case 'update':
                rename: bool = uniq_id != web_context.admin_event.uniq_id
                if rename:
                    event_loader.clear_cache(web_context.admin_event.uniq_id)
                    try:
                        EventDatabase(web_context.admin_event.uniq_id).rename(new_uniq_id=uniq_id)
                    except PermissionError as ex:
                        return AbstractController.redirect_error(
                            request, _('Renaming the database failed: {ex}.').format(ex=ex))
                with EventDatabase(uniq_id, write=True) as event_database:
                    event_database.update_stored_event(stored_event)
                    event_database.commit()
                if rename:
                    Message.success(
                        request,
                        _('Event [{old_uniq_id}] has been renamed ([{new_uniq_id}) and updated.').format(
                            olq_uniq_id=web_context.admin_event.uniq_id, new_uniq_id=uniq_id))
                else:
                    Message.success(request, _('Event [{uniq_id}] has been updated.').format(uniq_id=uniq_id))
                event_loader.clear_cache(uniq_id)
                return self._admin_event_config_render(request, event_uniq_id=uniq_id)
            case 'clone':
                EventDatabase(uniq_id).create()
                with EventDatabase(uniq_id, write=True) as event_database:
                    event_database.update_stored_event(stored_event)
                    event_database.commit()
                Message.success(request, _('Event [{uniq_id}] has been created.').format(uniq_id=uniq_id))
                event_loader.clear_cache(uniq_id)
                return self._admin_event_config_render(request, event_uniq_id=uniq_id)
            case 'delete':
                try:
                    arch = EventDatabase(web_context.admin_event.uniq_id).delete()
                except PermissionError as ex:
                    return AbstractController.redirect_error(request, 'Archiving the database failed: {ex}')
                event_loader.clear_cache(web_context.admin_event.uniq_id)
                Message.success(
                    request, _('Event [{uniq_id}] has been deleted, the database has been archived ({arch}).').format(
                        uniq_id=web_context.admin_event.uniq_id, arch=arch))
                return self._admin_render(AdminWebContext(request, data=None, admin_tab=None))
            case _:
                raise ValueError(f'action=[{action}]')

    @post(
        path='/admin/event-clone/{event_uniq_id:str}',
        name='admin-event-clone',
    )
    async def htmx_admin_event_clone(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_update(request, data=data, action='clone', event_uniq_id=event_uniq_id)

    @delete(
        path='/admin/event-delete/{event_uniq_id:str}',
        name='admin-event-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_event_delete(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_update(request, data=data, action='delete', event_uniq_id=event_uniq_id)

    @patch(
        path='/admin/event-update/{event_uniq_id:str}',
        name='admin-event-update'
    )
    async def htmx_admin_event_update(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_update(request, data=data, action='update', event_uniq_id=event_uniq_id)
