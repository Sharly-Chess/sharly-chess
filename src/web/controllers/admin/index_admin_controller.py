from datetime import datetime
from itertools import groupby
from logging import Logger
import time
from typing import Annotated, Any, cast

from litestar.exceptions import ClientException, NotFoundException

from common import (
    BASE_DIR,
    format_timestamp_date,
    format_timestamp_time,
)
from common.logger import get_logger
from common.network import NetworkMonitor
from data.access_levels.actions import AuthAction
from data.board import PlayerRatingType
from data.event import Event
from data.input_output import OnlineDataSourceManager
from data.loader import ArchiveLoader, EventLoader
from utils.types import Federation

from litestar import get, post, patch, delete
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate, ClientRedirect, Reswap
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, Redirect
from litestar.status_codes import HTTP_200_OK

from common.i18n import (
    _,
    locales,
)
from common.i18n.utils import locale_localized_name, by, unicode_normalize
from common.sharly_chess_config import SharlyChessConfig
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.config.config_store import (
    StoredConfig,
    StoredPlugin,
)
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredEvent
from database.sqlite.local_source_database import (
    LocalSourceDatabase,
    LocalSourceDatabaseManager,
    OutdatedActionManager,
    OutdatedDelayManager,
)
from database.sqlite.local_source_database.actions import (
    NotifOutdatedAction,
    OutdatedAction,
)
from database.sqlite.local_source_database.delays import (
    DisabledOutdatedDelay,
    OutdatedDelay,
)
from plugins.manager import plugin_manager
from utils import Utils
from utils.enum import FormAction, Result
from web.controllers.admin.base_admin_controller import (
    AdminWebContext,
    BaseAdminController,
)
from web.controllers.base_controller import WebContext
from web.guards import ActionGuard
from web.messages import Message
from web.session import SessionHandler
from web.urls import admin_event_tournaments_url, admin_event_url

logger: Logger = get_logger()


class IndexAdminController(BaseAdminController):
    @classmethod
    def _admin_validate_config_update_data(
        cls,
        data: dict[str, str] | None = None,
    ) -> StoredConfig:
        sharly_chess_config: SharlyChessConfig = SharlyChessConfig()
        if data is None:
            data = {}
        errors: dict[str, str] = {}
        experimental: bool = WebContext.form_data_to_bool(data, 'experimental')
        launch_browser: bool = WebContext.form_data_to_bool(data, 'launch_browser')
        federation_name: str | None = WebContext.form_data_to_str(
            data, field := 'federation'
        )
        federation: Federation | None = None
        if federation_name:
            if federation_name not in sharly_chess_config.federations:
                errors[field] = _('Invalid federation [{federation}].').format(
                    federation=federation_name
                )
                data[field] = ''
            else:
                federation = Federation(federation_name)
        else:
            errors[field] = _('Please choose a federation.')
        locale: str | None = WebContext.form_data_to_str(data, field := 'locale')
        if locale and locale not in locales:
            errors[field] = _('Invalid locale [{locale}].').format(locale=locale)
            data[field] = ''
        return StoredConfig(
            force_edit=False,
            console_log_level=sharly_chess_config.console_log_level,
            console_color=sharly_chess_config.console_color,
            console_show_date=sharly_chess_config.console_show_date,
            console_show_level=sharly_chess_config.console_show_level,
            experimental=experimental,
            launch_browser=launch_browser,
            federation=federation.name if federation else None,
            locale=locale,
            errors=errors,
        )

    @classmethod
    def _admin_validate_plugins_update_data(
        cls, data: dict[str, str] | None = None
    ) -> list[StoredPlugin]:
        if data is None:
            data = {}
        stored_plugins: list[StoredPlugin] = []
        for plugin in plugin_manager.all_plugins:
            if not plugin.is_state_editable:
                continue
            errors: dict[str, str] = {}
            stored_plugins.append(
                StoredPlugin(
                    name=plugin.id,
                    is_enabled=WebContext.form_data_to_bool(data, plugin.form_key),
                    errors=errors,
                )
            )
        return stored_plugins

    @classmethod
    def _admin_render(
        cls,
        web_context: AdminWebContext,
        template_context: dict[str, Any] | None = None,
        keep_modal_open: bool | None = None,
    ) -> Template:
        sorted_archives = ArchiveLoader.get_sorted_archives()
        public_only: bool = not web_context.client.can_view_private_events
        passed_events = EventLoader.get_events_metadata(
            'passed', public_only=public_only
        )
        current_events = EventLoader.get_events_metadata(
            'current', public_only=public_only
        )
        coming_events = EventLoader.get_events_metadata(
            'coming', public_only=public_only
        )
        lan_events = sorted(current_events + coming_events, key=by('name'))
        nav_tabs: dict[str, dict[str, Any]] = {
            'home': {
                'title': _('Home'),
                'template': 'index/home_tab.html',
                'icon_class': 'bi-house-fill',
                'disabled': False,
                'events': lan_events,
                'experimental_features_warning': True,
            },
        }
        if web_context.client.can_view_passed_events:
            nav_tabs |= {
                'current_events': {
                    'section_title': _('Events'),
                    'title': _('Current ({num})').format(
                        num=len(current_events) or '-'
                    ),
                    'template': 'index/events_tab.html',
                    'events': current_events,
                    'disabled': not current_events,
                    'empty_str': _('No current events.'),
                    'icon_class': 'bi-calendar indented',
                    'page_title': _('Current events'),
                    'divider': True,
                },
                'coming_events': {
                    'title': _('Upcoming ({num})').format(
                        num=len(coming_events) or '-'
                    ),
                    'template': 'index/events_tab.html',
                    'events': coming_events,
                    'disabled': not coming_events,
                    'empty_str': _('No upcoming events.'),
                    'icon_class': 'bi-calendar-check indented',
                    'page_title': _('Upcoming events'),
                },
                'passed_events': {
                    'title': _('Passed ({num})').format(num=len(passed_events) or '-'),
                    'template': 'index/events_tab.html',
                    'events': passed_events,
                    'disabled': not passed_events,
                    'empty_str': _('No passed events.'),
                    'icon_class': 'bi-calendar-minus indented',
                    'page_title': _('Passed events'),
                },
                'archives': {
                    'title': _('Archived ({num})').format(
                        num=len(sorted_archives) or '-'
                    ),
                    'template': 'index/archives_tab.html',
                    'archives': sorted_archives,
                    'disabled': not sorted_archives,
                    'empty_str': _('No archived events.'),
                    'icon_class': 'bi-archive indented',
                    'page_title': _('Archived events'),
                },
            }
        else:
            nav_tabs |= {
                'home': {
                    'title': _('Events ({num})').format(num=len(lan_events) or '-'),
                    'template': 'index/home_tab.html',
                    'events': lan_events,
                    'disabled': False,
                    'empty_str': _('No events.'),
                    'icon_class': 'bi-house-fill',
                    'page_title': _('Events'),
                    'divider': True,
                },
            }
        if (not template_context or 'modal' not in template_context) and (
            not web_context.admin_tab or nav_tabs[web_context.admin_tab]['disabled']
        ):
            web_context.admin_tab = list(nav_tabs.keys())[0]
        for nav_index in range(len(nav_tabs)):
            if (
                web_context.admin_tab == list(nav_tabs.keys())[nav_index]
                and nav_tabs[web_context.admin_tab]['disabled']
            ):
                web_context.admin_tab = list(nav_tabs.keys())[
                    (nav_index + 1) % len(nav_tabs)
                ]

        svg_logo = (BASE_DIR / 'src/web/static/images/sharly-chess-logo.svg').read_text(
            encoding='utf-8'
        )

        context = (
            web_context.template_context
            | {
                'messages': Message.messages(web_context.request),
                'format_timestamp_date': format_timestamp_date,
                'format_timestamp_time': format_timestamp_time,
                'nav_tabs': nav_tabs,
                'svg_logo': svg_logo,
                'admin_events_show_details': (
                    SessionHandler.get_session_admin_events_show_details(
                        web_context.request
                    )
                ),
            }
            | (template_context or {})
        )

        if 'modal' in context:
            return HTMXTemplate(
                template_name='admin/modals.html',
                context=context,
                re_target='#modal-wrapper',
                trigger_event='modal_opened'
                if not keep_modal_open
                else 'static_modal_opened',
                after='settle',
            )
        return HTMXTemplate(template_name='admin/index.html', context=context)

    @get(
        path='/{admin_tab:str}',
        name='admin-tab',
    )
    async def htmx_admin_tab(
        self,
        request: HTMXRequest,
        admin_tab: str,
        admin_events_show_details: bool | None,
    ) -> Template:
        web_context = AdminWebContext(request, admin_tab=admin_tab)

        if admin_events_show_details is not None:
            SessionHandler.set_session_admin_events_show_details(
                request, admin_events_show_details
            )

        return self._admin_render(web_context=web_context)

    @classmethod
    def _prepare_event_modal_data(
        cls,
        action: str,
        request: HTMXRequest,
        admin_event: Event | None,
    ) -> dict[str, Any]:
        match action:
            case 'update':
                if admin_event is None:
                    raise RuntimeError(f'{admin_event=} for [{action=}]')
                name = admin_event.stored_event.name
                uniq_id = admin_event.stored_event.uniq_id
            case 'clone':
                if admin_event is None:
                    raise RuntimeError(f'{admin_event=} for [{action=}]')
                name = EventLoader.get(request).get_unused_event_name(
                    admin_event.stored_event.name
                )
                uniq_id = EventLoader.get(request).get_unused_event_uniq_id(
                    admin_event.stored_event.uniq_id
                )
            case 'create':
                name = EventLoader.get(request).get_unused_event_name(_('New event'))
                uniq_id = EventLoader.get(request).get_unused_event_uniq_id(_('event'))
            case _:
                raise ValueError(f'action=[{action}]')
        match action:
            case 'update' | 'clone':
                assert admin_event is not None
                start = admin_event.stored_event.start
                stop = admin_event.stored_event.stop
            case 'create':
                today_str: str = format_timestamp_date()
                start = time.mktime(
                    datetime.strptime(
                        f'{today_str} 00:00', '%Y-%m-%d %H:%M'
                    ).timetuple()
                )
                stop = time.mktime(
                    datetime.strptime(
                        f'{today_str} 23:59', '%Y-%m-%d %H:%M'
                    ).timetuple()
                )
            case _:
                raise ValueError(f'action=[{action}]')
        background_color: str | None = None
        location: str | None = None
        player_rating_type: int
        record_illegal_moves: int | None = None
        three_points_for_a_win: bool
        pab_value: int
        rules: str | None = None
        message_text: str | None = None
        message_color: str | None = None
        message_background_color: str | None = None
        prize_currency: str | None = None
        stored_plugin_data: dict[str, dict[str, Any]] = {}
        match action:
            case 'update' | 'clone':
                if admin_event is None:
                    raise RuntimeError(f'{admin_event=} for [{action=}]')
                stored_event = admin_event.stored_event
                public = stored_event.public
                federation = stored_event.federation
                background_color = stored_event.background_color
                location = stored_event.location
                player_rating_type = stored_event.player_rating_type
                record_illegal_moves = stored_event.record_illegal_moves
                rules = stored_event.rules
                message_text = stored_event.message_text
                message_color = admin_event.message_color
                message_background_color = admin_event.message_background_color
                prize_currency = stored_event.prize_currency
                override_unrated_rapid_blitz = stored_event.override_unrated_rapid_blitz
                three_points_for_a_win = stored_event.three_points_for_a_win
                pab_value = stored_event.pab_value
                stored_plugin_data = stored_event.plugin_data
            case 'create':
                sharly_chess_config: SharlyChessConfig = SharlyChessConfig()
                public = False
                background_color = sharly_chess_config.default_background_color
                message_background_color = (
                    sharly_chess_config.default_message_background_color
                )
                message_color = sharly_chess_config.default_message_color
                federation = (
                    sharly_chess_config.federation.name
                    if sharly_chess_config.federation
                    else ''
                )
                player_rating_type = PlayerRatingType.FIDE.value
                override_unrated_rapid_blitz = True
                three_points_for_a_win = False
                pab_value = Result.WIN.value
            case _:
                raise ValueError(f'action=[{action}]')

        plugin_form_data: dict[str, str] = {}
        for (
            plugin_id,
            plugin_data_class,
        ) in Event.plugin_data_class_by_plugin_id().items():
            plugin_form_data |= plugin_data_class.from_stored_value(
                stored_plugin_data.get(plugin_id, {})
            ).to_form_data(action=action)

        return {
            'uniq_id': WebContext.value_to_form_data(uniq_id),
            'name': WebContext.value_to_form_data(name),
            'public': WebContext.value_to_form_data(public),
            'federation': WebContext.value_to_form_data(federation),
            'start': WebContext.value_to_datetime_form_data(start),
            'stop': WebContext.value_to_datetime_form_data(stop),
            'player_rating_type': WebContext.value_to_form_data(player_rating_type),
            'background_color': WebContext.value_to_form_data(background_color),
            'location': WebContext.value_to_form_data(location),
            'record_illegal_moves': WebContext.value_to_form_data(record_illegal_moves),
            'rules': WebContext.value_to_form_data(rules),
            'message_text': WebContext.value_to_form_data(message_text),
            'message_color': WebContext.value_to_form_data(message_color),
            'message_background_color': WebContext.value_to_form_data(
                message_background_color
            ),
            'prize_currency': WebContext.value_to_form_data(prize_currency),
            'override_unrated_rapid_blitz': WebContext.value_to_form_data(
                override_unrated_rapid_blitz
            ),
            'three_points_for_a_win': WebContext.value_to_form_data(
                three_points_for_a_win
            ),
            'pab_value': WebContext.value_to_form_data(pab_value),
        } | plugin_form_data

    @classmethod
    def _read_event_form_data(
        cls,
        action: FormAction,
        web_context: WebContext,
        admin_event: Event | None,
        data: dict[str, str] | None = None,
    ) -> tuple[StoredEvent | None, dict[str, str]]:
        if data is None:
            data = {}
        uniq_id: str | None
        errors: dict[str, str] = {}
        start: float | None = None
        stop: float | None = None

        message_color: str | None = None
        message_background_color: str | None = None

        name = WebContext.form_data_to_str(data, field := 'name') or ''
        if not name:
            errors[field] = _('Please enter the name of the event.')
        if action == 'update' and web_context.client.can_rename_event:
            assert admin_event is not None
            uniq_id = admin_event.uniq_id
        else:
            uniq_id = EventLoader().get_unused_event_uniq_id(
                Utils.name_to_uniq_id(name)
            )

        federation = WebContext.form_data_to_str(data, field := 'federation', '') or ''
        if federation not in SharlyChessConfig.federations:
            # should never happen, not translated.
            errors[field] = f'Invalid federation value [{data[field]}].'
            data[field] = ''
        start_str: str | None = WebContext.form_data_to_str(data, field := 'start')
        if not start_str:
            errors[field] = _('Please enter the start date of the event.')
        else:
            start = time.mktime(
                datetime.strptime(start_str, '%Y-%m-%dT%H:%M').timetuple()
            )
        stop_str: str | None = WebContext.form_data_to_str(data, field := 'stop')
        if not stop_str:
            errors[field] = _('Please enter the end date of the event.')
        else:
            stop = time.mktime(
                datetime.strptime(stop_str, '%Y-%m-%dT%H:%M').timetuple()
            )
        if (
            start
            and stop
            and 'start' not in errors
            and 'stop' not in errors
            and start > stop
        ):
            errors[field] = _('Please enter a date after the start date.')
        public = WebContext.form_data_to_bool(data, 'public')
        location = WebContext.form_data_to_str(data, 'location')
        player_rating_type: int = (
            WebContext.form_data_to_int(data, 'player_rating_type')
            or PlayerRatingType.FIDE.value
        )

        background_color = cls._admin_validate_background_color_update_data(
            data, errors
        )
        record_illegal_moves = cls._admin_validate_record_illegal_moves_update_data(
            data, errors
        )
        rules = cls._admin_validate_rules_update_data(data, errors)
        field = 'message_text'
        message_text = WebContext.form_data_to_str(data, field)
        field = 'message_color'
        if not WebContext.form_data_to_bool(data, field + '_checkbox'):
            try:
                message_color = WebContext.form_data_to_rgb(data, field)
            except ValueError:
                errors[field] = _(
                    'Invalid color [{color}] ([#RRGGBB] expected).'
                ).format(color={data[field]})
        field = 'message_background_color'
        if not WebContext.form_data_to_bool(data, field + '_checkbox'):
            try:
                message_background_color = WebContext.form_data_to_rgb(data, field)
            except ValueError:
                errors[field] = _(
                    'Invalid color [{color}] ([#RRGGBB] expected).'
                ).format(color={data[field]})
        prize_currency = WebContext.form_data_to_str(data, 'prize_currency')
        override_unrated_rapid_blitz = WebContext.form_data_to_bool(
            data, 'override_unrated_rapid_blitz'
        )
        three_points_for_a_win = WebContext.form_data_to_bool(
            data, 'three_points_for_a_win'
        )
        pab_value = WebContext.form_data_to_int(data, 'pab_value') or Result.WIN.value

        plugin_manager.hook.validate_event_form_fields(
            action=action, event=admin_event, data=data, errors=errors
        )

        plugin_data: dict[str, dict[str, Any]] = {}
        for (
            plugin_id,
            plugin_data_class,
        ) in Event.plugin_data_class_by_plugin_id().items():
            previous_object = None
            if admin_event is not None:
                previous_object = admin_event.plugin_data.get(plugin_id)

            plugin_data[plugin_id] = plugin_data_class.from_form_data(
                data, action=action, previous_object=previous_object
            ).to_stored_value()

        plugin_data: dict[str, dict[str, Any]] = {
            plugin_id: plugin_data_class.from_form_data(
                data, action=action
            ).to_stored_value()
            for plugin_id, plugin_data_class in Event.plugin_data_class_by_plugin_id().items()
        }

        assert start is not None
        assert stop is not None

        if errors:
            return None, errors

        stored_event = StoredEvent(
            uniq_id=uniq_id,
            name=name,
            federation=federation,
            start=start,
            stop=stop,
            public=bool(public),
            location=location,
            player_rating_type=player_rating_type,
            background_color=background_color,
            record_illegal_moves=record_illegal_moves,
            rules=rules,
            message_text=message_text,
            message_color=message_color,
            message_background_color=message_background_color,
            prize_currency=prize_currency,
            override_unrated_rapid_blitz=override_unrated_rapid_blitz,
            three_points_for_a_win=three_points_for_a_win,
            pab_value=pab_value,
            # Timer defaults are edited in the timers tab.  We copy the values from the admin_event if it exists.
            timer_colors={
                i: admin_event.timer_colors[i] if admin_event else None
                for i in range(1, 4)
            }
            if admin_event
            else None,
            timer_delays={
                i: admin_event.timer_delays[i] if admin_event else None
                for i in range(1, 4)
            }
            if admin_event
            else None,
            plugin_data=plugin_data,
        )
        return stored_event, errors

    def _event_modal_context(
        self,
        web_context: AdminWebContext,
        action: FormAction,
        data: dict[str, str],
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        event = web_context.admin_event
        plugin_form_fields_templates = (
            plugin_manager.hook_for_event(event, 'get_event_form_fields_template')()
            or []
        )
        template_context = {
            'federation_options': self._get_federation_options(),
            'timer_color_texts': self._get_timer_color_texts(
                SharlyChessConfig.default_timer_delays
            ),
            'modal': 'event',
            'event_uniq_ids': list(EventLoader().event_uniq_ids),
            'plugin_form_fields_templates': plugin_form_fields_templates,
            'player_rating_type_options': {
                str(PlayerRatingType.FIDE.value): _('FIDE'),
                str(PlayerRatingType.NATIONAL.value): _(
                    'National *** NAME FOR RATING TYPE NATIONAL'
                ),
            },
            'three_points_for_a_win_options': {
                str(Result.WIN.value): _('Win'),
                str(Result.DRAW.value): _('Draw'),
                str(Result.LOSS.value): _('Loss'),
            },
            'action': action,
            'data': data,
            'errors': errors or {},
        }
        return template_context

    @get(
        path=[
            '/{admin_tab:str}/event-modal/{action:str}',
            '/{admin_tab:str}/event-modal/{action:str}/{event_uniq_id:str}',
            '/event-modal/{action:str}/{event_uniq_id:str}',
        ],
        name='admin-event-modal',
        guards=[ActionGuard(AuthAction.VIEW_EVENT_CONFIG)],
    )
    async def htmx_admin_tab_event_create_modal(
        self,
        request: HTMXRequest,
        action: FormAction,
        admin_tab: str | None = None,
    ) -> Template:
        web_context = AdminWebContext(request, admin_tab=admin_tab)
        data = self._prepare_event_modal_data(action, request, web_context.admin_event)
        template_context = self._event_modal_context(
            web_context,
            action,
            data,
        )

        return self._admin_render(
            web_context=web_context,
            template_context=template_context,
        )

    @post(
        path='/{admin_tab:str}/create-event',
        name='admin-tab-create-event',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_tab_event_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        admin_tab: str,
    ) -> Template | Redirect:
        web_context = AdminWebContext(request, admin_tab=admin_tab)
        stored_event, errors = self._read_event_form_data(
            FormAction.CREATE, web_context, None, data
        )
        if not stored_event:
            template_context = self._event_modal_context(
                web_context, FormAction.CREATE, data, errors=errors
            )
            return self._admin_render(
                web_context=web_context,
                template_context=template_context,
            )

        uniq_id: str = stored_event.uniq_id
        EventDatabase(uniq_id).create()
        with EventDatabase(uniq_id, write=True) as event_database:
            event_database.update_stored_event(stored_event)
        Message.success(
            request, _('Event [{uniq_id}] has been created.').format(uniq_id=uniq_id)
        )
        return Redirect(admin_event_url(request, event_uniq_id=uniq_id))

    @get(
        path='/{admin_tab:str}/event-modal/delete/{event_uniq_id:str}',
        name='admin-event-delete-modal',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_event_delete_modal(
        self, request: HTMXRequest, admin_tab: str
    ) -> Template:
        web_context = AdminWebContext(request, admin_tab=admin_tab)
        return self._admin_render(web_context, {'modal': 'event-delete'})

    @delete(
        path='/{admin_tab:str}/event-delete/{event_uniq_id:str}',
        name='admin-event-delete',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_event_delete(
        self, request: HTMXRequest, admin_tab: str
    ) -> Template:
        web_context = AdminWebContext(request, admin_tab=admin_tab)
        event = web_context.get_admin_event()
        try:
            arch = EventDatabase(event.uniq_id).delete()
        except PermissionError as ex:
            raise ClientException(f'Archiving the database failed: {ex}')

        Message.success(
            request,
            _(
                'Event [{uniq_id}] has been deleted, the database has been archived ({arch}).'
            ).format(uniq_id=event.uniq_id, arch=arch),
        )

        return self._admin_render(web_context)

    @post(
        path='/event-clone/{event_uniq_id:str}',
        name='admin-event-clone',
        guards=[ActionGuard(AuthAction.MANAGE_EVENTS)],
    )
    async def htmx_admin_event_clone(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        web_context = AdminWebContext(request)
        stored_event, errors = self._read_event_form_data(
            FormAction.CLONE, web_context, web_context.admin_event, data
        )
        if not stored_event:
            template_context = self._event_modal_context(
                web_context, FormAction.CLONE, data, errors=errors
            )
            return self._admin_render(
                web_context=web_context,
                template_context=template_context,
            )

        uniq_id: str = stored_event.uniq_id
        event = web_context.get_admin_event()
        EventDatabase(event.uniq_id).clone(new_uniq_id=uniq_id)
        with EventDatabase(uniq_id, write=True) as event_database:
            event_database.update_stored_event(stored_event)
            if 'with_players' not in data:
                event_database.delete_all_stored_players()
            plugin_manager.hook.on_event_duplicated(event_database=event_database)

        Message.success(
            request,
            _('Event [{uniq_id}] has been created.').format(uniq_id=uniq_id),
        )
        return ClientRedirect(redirect_to=admin_event_tournaments_url(request, uniq_id))

    @patch(
        path=[
            '/event-update/{event_uniq_id:str}',
            '/{admin_tab:str}/event-update/{event_uniq_id:str}',
        ],
        name='admin-event-update',
        guards=[ActionGuard(AuthAction.UPDATE_EVENT)],
    )
    async def htmx_admin_event_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        admin_tab: str | None,
    ) -> Template:
        web_context = AdminWebContext(request, admin_tab=admin_tab)
        stored_event, errors = self._read_event_form_data(
            FormAction.UPDATE, web_context, web_context.admin_event, data
        )
        if not stored_event:
            template_context = self._event_modal_context(
                web_context, FormAction.UPDATE, data, errors=errors
            )
            return self._admin_render(
                web_context=web_context,
                template_context=template_context,
            )

        all_plugins = plugin_manager.enabled_plugins or []
        enabled_before = [
            p for p in all_plugins if p.is_enabled_for_event(web_context.admin_event)
        ]

        uniq_id = stored_event.uniq_id
        with EventDatabase(uniq_id, write=True) as event_database:
            event_database.update_stored_event(stored_event)

        web_context = AdminWebContext(request, admin_tab=admin_tab, reload_event=True)
        enabled_after = [
            p for p in all_plugins if p.is_enabled_for_event(web_context.admin_event)
        ]
        disabled_plugins = [p for p in enabled_before if p not in enabled_after]

        if disabled_plugins:
            message = (
                _(
                    'Due to the federation change, the following plugins have been disabled for this event: <b>{plugins}</b>.'
                ).format(plugins=', '.join(p.name for p in disabled_plugins))
                if len(disabled_plugins) > 1
                else _(
                    'Due to the federation change, the following plugin has been disabled for this event: <b>{plugin}</b>.'
                ).format(plugin=disabled_plugins[0].name)
            )
            Message.warning(
                request,
                message,
            )
        else:
            Message.success(
                request,
                _('Event [{uniq_id}] has been updated.').format(uniq_id=uniq_id),
            )

        return HTMXTemplate(
            template_name='common/empty_modal_and_messages.html',
            context={'messages': Message.messages(request)},
            re_target='#modal-wrapper',
            trigger_event='close_modal',
            after='settle',
        )

    @patch(
        path='/event-uniq-id-update/{event_uniq_id:str}',
        name='admin-event-uniq-id-update',
        guards=[ActionGuard(AuthAction.RENAME_EVENT)],
    )
    async def htmx_admin_event_uniq_id_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> ClientRedirect:
        web_context = AdminWebContext(request)
        event = web_context.get_admin_event()
        new_uniq_id = WebContext.form_data_to_str(data, 'uniq_id')
        if (
            not new_uniq_id
            or not SharlyChessConfig.uniq_id_regex.match(new_uniq_id)
            or (
                new_uniq_id != event.uniq_id
                and new_uniq_id in EventLoader.all_event_ids()
            )
        ):
            # No precise error (validated in JS)
            raise ClientException(f'Invalid event uniq ID [{new_uniq_id}].')
        if new_uniq_id != event.uniq_id:
            try:
                EventDatabase(event.uniq_id).rename(new_uniq_id)
            except PermissionError as ex:
                raise ClientException(f'Renaming the database failed: {ex}.')
            Message.success(
                request,
                _(
                    'Event unique ID has been renamed from '
                    '[{old_uniq_id}] to [{new_uniq_id}].'
                ).format(
                    old_uniq_id=event.uniq_id,
                    new_uniq_id=new_uniq_id,
                ),
            )
        return ClientRedirect(redirect_to=admin_event_url(request, new_uniq_id))

    @post(
        path='/restore-archive/{archive_name:str}',
        name='admin-restore-archive',
        guards=[ActionGuard(AuthAction.MANAGE_ARCHIVES)],
    )
    async def htmx_admin_restore_archive(
        self,
        request: HTMXRequest,
        archive_name: str,
    ) -> Template:
        web_context = AdminWebContext(request, admin_tab='archives')
        archive = ArchiveLoader.get_archive(archive_name)
        if not archive:
            raise NotFoundException(f'Unknown archive [{archive_name}]')
        uniq_id = archive.restore()
        Message.success(
            request,
            _(
                'Archive [{archive}] successfully restored (see event [{event}]).'
            ).format(archive=archive.name, event=uniq_id),
        )
        return self._admin_render(web_context=web_context)

    @patch(
        path='/locale-update/{locale:str}',
        name='admin-locale-update',
    )
    async def htmx_admin_locale_update(
        self, request: HTMXRequest, locale: str
    ) -> Template:
        web_context = AdminWebContext(request)
        sharly_chess_config: SharlyChessConfig = SharlyChessConfig()
        if locale in locales:
            stored_config: StoredConfig = sharly_chess_config.stored_config
            stored_config.locale = locale
            with ConfigDatabase(write=True) as config_database:
                config_database.update_stored_config(sharly_chess_config.stored_config)
            sharly_chess_config.load_and_set_env()
        return self._admin_render(web_context=web_context)

    def _config_modal_context(
        self,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        config = SharlyChessConfig()
        if data is None:
            data = WebContext.values_dict_to_form_data(
                {
                    'console_log_level': config.console_log_level,
                    'console_color': config.console_color,
                    'console_show_date': config.console_show_date,
                    'console_show_level': config.console_show_level,
                    'experimental': config.experimental,
                    'launch_browser': config.launch_browser,
                    'federation': config.stored_config.federation,
                    'locale': config.locale,
                }
            )

        for plugin in plugin_manager.all_plugins:
            if plugin.form_key not in data:
                data[plugin.form_key] = WebContext.value_to_form_data(plugin.is_enabled)

        if errors is None:
            errors = {}

        locale_options: dict[str, str] = {
            locale: locale_localized_name(locale) for locale in locales
        }

        all_plugins = sorted(
            plugin_manager.all_plugins, key=lambda p: unicode_normalize(p.name)
        )

        plugins_by_federation = {
            federation: list(group)
            for federation, group in groupby(
                all_plugins, key=lambda p: getattr(p, 'federation', None)
            )
        }

        global_plugins = plugins_by_federation.pop(None, [])

        plugins_by_federation = {
            SharlyChessConfig.federations.get(
                cast(str, code_key), str(code_key)
            ): plugins
            for code_key, plugins in sorted(
                plugins_by_federation.items(),
                key=lambda kv: SharlyChessConfig.federations.get(cast(str, kv[0]), ''),
            )
        }

        template_context = {
            'locale_options': locale_options,
            'global_plugins': global_plugins,
            'federation_plugins': plugins_by_federation,
            'federation_options': (
                {} if data['federation'] else {'': _('Please choose a federation')}
            )
            | self._get_federation_options(),
            'modal': 'config',
            'data': data,
            'errors': errors,
        }

        return template_context

    @get(
        path='/config-modal',
        name='admin-config-modal',
        guards=[ActionGuard(AuthAction.MANAGE_APPLICATION_SETTINGS)],
    )
    async def htmx_admin_config_modal(self, request: HTMXRequest) -> Template:
        config = SharlyChessConfig()
        web_context = AdminWebContext(request)
        template_context = self._config_modal_context()
        return self._admin_render(
            web_context=web_context,
            template_context=template_context,
            keep_modal_open=config.force_edit,
        )

    @patch(
        path='/config-update',
        name='admin-config-update',
        guards=[ActionGuard(AuthAction.MANAGE_APPLICATION_SETTINGS)],
    )
    async def htmx_admin_config_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = AdminWebContext(request)
        stored_config: StoredConfig = self._admin_validate_config_update_data(data)
        stored_plugins: list[StoredPlugin] = self._admin_validate_plugins_update_data(
            data
        )
        errors = stored_config.errors
        for plugin in stored_plugins:
            errors |= plugin.errors
        if errors:
            template_context = self._config_modal_context(data, errors)
            sharly_chess_config: SharlyChessConfig = SharlyChessConfig()
            return self._admin_render(
                web_context=web_context,
                template_context=template_context,
                keep_modal_open=sharly_chess_config.force_edit,
            )

        with ConfigDatabase(write=True) as config_database:
            stored_config.force_edit = False
            config_database.update_stored_config(stored_config)
            for stored_plugin in stored_plugins:
                config_database.update_stored_plugin(stored_plugin)
        SharlyChessConfig().load_and_set_env()
        Message.success(request, _('Sharly Chess settings have been updated.'))
        return HTMXTemplate(
            template_name='common/empty_modal_and_messages.html',
            context={'messages': Message.messages(request)},
            re_target='#modal-wrapper',
            trigger_event='close_modal',
            after='receive',
        )

    @get(
        path='/database-status-badge',
        name='admin-database-status-badge',
        guards=[ActionGuard(AuthAction.MANAGE_SOURCE_DATABASES)],
    )
    async def htmx_admin_status_badge(
        self,
        request: HTMXRequest,
    ) -> Template:
        source_databases: list[LocalSourceDatabase] = (
            LocalSourceDatabaseManager().objects()
        )
        for database in source_databases:
            database.check()
            if database.update_status is not None:
                if database.update_status:
                    Message.success(
                        request,
                        _('Database [{database}] successfully updated.').format(
                            database=database.name
                        ),
                    )
                else:
                    Message.error(
                        request,
                        _('Error when updating database [{database}].').format(
                            database=database.name
                        ),
                    )
                database.__class__.update_status = None

        if any([database.is_updating for database in source_databases]):
            template_name = '/admin/common/database/updating_badge.html'
        elif any([database.outdated_warning for database in source_databases]):
            template_name = '/admin/common/database/out_of_date_badge.html'
        else:
            template_name = '/admin/common/database/settings_badge.html'
        return HTMXTemplate(
            template_name='/admin/common/database/database_badge_and_messages.html',
            context={
                'badge': template_name,
                'messages': Message.messages(request),
            },
        )

    @staticmethod
    def _database_modal_context() -> dict[str, Any]:
        return {
            'databases': LocalSourceDatabaseManager().objects(),
            'online_data_sources': OnlineDataSourceManager().objects(),
            'network_connected': NetworkMonitor.connected(),
            'outdate_delay_options': OutdatedDelayManager().options(),
            'outdate_action_options': OutdatedActionManager().options(),
            'modal': 'database',
        }

    @get(
        path='/database-modal',
        name='admin-database-modal',
        guards=[ActionGuard(AuthAction.MANAGE_SOURCE_DATABASES)],
    )
    async def htmx_admin_database_modal(self, request: HTMXRequest) -> Template:
        web_context = AdminWebContext(request)
        template_context = self._database_modal_context()
        return self._admin_render(
            web_context=web_context,
            template_context=template_context,
        )

    @patch(
        path='/database-options-update/{database_id:str}',
        name='admin-database-options-update',
        guards=[ActionGuard(AuthAction.MANAGE_SOURCE_DATABASES)],
    )
    async def _database_options_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        database_id: str,
    ) -> Template:
        database = LocalSourceDatabaseManager().get_object(database_id)
        stored_database = database.stored_source_database
        delay: OutdatedDelay = DisabledOutdatedDelay()
        if delay_id := WebContext.form_data_to_str(data, 'outdate_delay'):
            delay = OutdatedDelayManager().get_object(delay_id)
        action: OutdatedAction = NotifOutdatedAction()
        if action_id := WebContext.form_data_to_str(data, 'outdate_action'):
            action = OutdatedActionManager().get_object(action_id)
        stored_database.outdate_delay = delay.id
        stored_database.outdate_action = action.id
        with ConfigDatabase(write=True) as config_database:
            config_database.update_stored_local_source_database(stored_database)
        database.check()
        return HTMXTemplate(
            template_name='admin/common/database/database_row.html',
            context=self._database_modal_context() | {'database': database},
        )

    @get(
        path='/database-status/{database_id:str}',
        name='admin-database-status',
        guards=[ActionGuard(AuthAction.MANAGE_SOURCE_DATABASES)],
    )
    async def _database_update_status(self, database_id: str) -> Template:
        database = LocalSourceDatabaseManager().get_object(database_id)
        return HTMXTemplate(
            template_name='/admin/common/database/database_update_buttons.html',
            context={'database': database},
        )

    @post(
        path='/database-update/{database_id:str}',
        name='admin-database-update',
        guards=[ActionGuard(AuthAction.MANAGE_SOURCE_DATABASES)],
    )
    async def _database_update(self, database_id: str) -> Reswap:
        database = LocalSourceDatabaseManager().get_object(database_id)
        database.update()
        return Reswap(content=None, method='none', status_code=HTTP_200_OK)

    @delete(
        path='/database-delete/{database_id:str}',
        name='admin-database-delete',
        guards=[ActionGuard(AuthAction.MANAGE_SOURCE_DATABASES)],
        status_code=HTTP_200_OK,
    )
    async def _database_delete(self, database_id: str) -> Template:
        try:
            database = LocalSourceDatabaseManager().get_object(database_id)
            database.delete()
        except KeyError:
            raise NotFoundException(f'Unknown database [{database_id}].')
        return HTMXTemplate(
            template_name='/admin/common/database/database_update_buttons.html',
            context={'database': database},
        )

    @post(
        path='/online-data-source/check/{data_source_id:str}',
        name='admin-online-data-source-check',
        guards=[ActionGuard(AuthAction.MANAGE_SOURCE_DATABASES)],
    )
    async def htmx_admin_data_source_check(
        self,
        request: HTMXRequest,
        data_source_id: str,
    ) -> Template:
        web_context = AdminWebContext(request)
        try:
            data_source = OnlineDataSourceManager().get_object(data_source_id)
            await data_source.reload_connection_status()
        except KeyError:
            raise NotFoundException(f'Unknown data source [{data_source_id}].')
        template_context = self._database_modal_context()
        return self._admin_render(
            web_context=web_context,
            template_context=template_context,
        )
