import logging
from datetime import datetime
from logging import Logger
from typing import Annotated, Any

from common import format_timestamp_date, format_timestamp_time
from common.logger import get_logging_config, get_logger
from common.network import NetworkMonitor
from data.auth.mode import Mode
from data.input_output import OnlineDataSourceManager
from data.loader import ArchiveLoader, EventLoader
from data.player import Federation
from database.access.access_database import access_driver, odbc_drivers

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
from common.i18n.utils import (
    locale_localized_name,
)
from common.sharly_chess_config import SharlyChessConfig
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.config.config_store import (
    StoredConfig,
    StoredPlugin,
    StoredLocalSourceDatabase,
)
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredEvent
from database.sqlite.local_source_database import (
    LocalSourceDatabase,
    LocalSourceDatabaseManager,
    OutdatedActionManager,
    OutdatedDelayManager,
)
from database.sqlite.local_source_database.actions import NotifOutdatedAction
from database.sqlite.local_source_database.delays import DisabledOutdatedDelay
from plugins.manager import plugin_manager
from web.controllers.admin.base_admin_controller import (
    AdminWebContext,
    BaseAdminController,
)
from web.controllers.base_controller import WebContext
from web.messages import Message
from web.session import SessionHandler
from web.urls import admin_event_url

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
        console_log_level: int | None = WebContext.form_data_to_int(
            data, field := 'console_log_level'
        )
        if (
            console_log_level
            and console_log_level not in sharly_chess_config.console_log_levels
        ):
            errors[field] = _(
                'Invalid console logging level [{console_log_level}].'
            ).format(log_level=console_log_level)
            data[field] = ''
        console_color: bool = WebContext.form_data_to_bool(data, 'console_color')
        console_show_date: bool = WebContext.form_data_to_bool(
            data, 'console_show_date'
        )
        console_show_level: bool = WebContext.form_data_to_bool(
            data, 'console_show_level'
        )
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
        locale: str | None = WebContext.form_data_to_str(data, field := 'locale')
        if locale and locale not in locales:
            errors[field] = _('Invalid locale [{locale}].').format(locale=locale)
            data[field] = ''
        default_mode: int = (
            WebContext.form_data_to_int(data, 'default_mode') or Mode.STAND_ALONE.value
        )
        return StoredConfig(
            force_edit=False,
            console_log_level=console_log_level,
            console_color=console_color,
            console_show_date=console_show_date,
            console_show_level=console_show_level,
            experimental=experimental,
            launch_browser=launch_browser,
            federation=federation.name if federation else None,
            locale=locale,
            default_mode=default_mode,
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
        request: HTMXRequest,
        admin_tab: str | None,
        modal: str | None = None,
        keep_modal_open: bool | None = None,
        admin_events_show_details: bool | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: AdminWebContext = AdminWebContext(
            request, data=None, admin_tab=admin_tab
        )
        if web_context.error:
            return web_context.error
        if admin_events_show_details is not None:
            SessionHandler.set_session_admin_events_show_details(
                request, admin_events_show_details
            )

        sharly_chess_config: SharlyChessConfig = SharlyChessConfig()
        archive_loader: ArchiveLoader = ArchiveLoader.get(request=web_context.request)
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
        nav_tabs: dict[str, dict[str, Any]] = {
            'home': {
                'title': _('Home'),
                'template': 'index/home_tab.html',
                'icon_class': 'bi-qr-code',
                'disabled': False,
                'experimental_features_warning': True,
            },
            'current_events': {
                'section_title': _('Events'),
                'title': _('Current ({num})').format(num=len(current_events) or '-'),
                'template': 'index/events_tab.html',
                'events': current_events,
                'disabled': not current_events,
                'empty_str': _('No current events.'),
                'icon_class': 'bi-calendar indented',
                'page_title': _('Current events'),
            },
            'coming_events': {
                'title': _('Upcoming ({num})').format(num=len(coming_events) or '-'),
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
                    num=len(archive_loader.archives_sorted_by_date) or '-'
                ),
                'template': 'index/archives_tab.html',
                'archives': archive_loader.archives_sorted_by_date,
                'disabled': not archive_loader.archives_sorted_by_date,
                'empty_str': _('No archived events.'),
                'icon_class': 'bi-archive indented',
                'page_title': _('Archived events'),
            },
        }
        if web_context.client.can_view_application_settings:
            nav_tabs |= {
                'config': {
                    'divider': True,
                    'title': _('Settings'),
                    'template': 'index/config_tab.html',
                    'icon_class': 'bi-gear',
                    'disabled': False,
                },
            }
            if sharly_chess_config.force_edit:
                web_context.admin_tab = 'config'
        if not modal and (
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

        event_card_blocks = plugin_manager.hook.get_event_card_block_template()

        console_level_infos: dict[int, dict[str, int | str]] = {
            logging.DEBUG: {
                'text': _('Debug message'),
                'color': '#808080',
            },
            logging.INFO: {
                'text': _('Information message'),
                'color': '#ffffff',
            },
            logging.WARNING: {
                'text': _('Warning message'),
                'color': '#a68a0d',
            },
            logging.ERROR: {
                'text': _('Error message'),
                'color': '#f0524f',
            },
        }
        for value, name in SharlyChessConfig.console_log_levels.items():
            console_level_infos[value]['name'] = name

        context = web_context.template_context | {
            'odbc_drivers': odbc_drivers(),
            'access_driver': access_driver(),
            'plugins': plugin_manager.all_plugins,
            'messages': Message.messages(web_context.request),
            'nav_tabs': nav_tabs,
            'admin_events_show_details': (
                SessionHandler.get_session_admin_events_show_details(
                    web_context.request
                )
            ),
            'event_card_blocks': event_card_blocks,
            'row_cycler': cls.get_cycler(['odd', 'even']),
            'format_timestamp_date': format_timestamp_date,
            'format_timestamp_time': format_timestamp_time,
            'console_level_infos': console_level_infos,
            'console_formatted_current_date': datetime.today().strftime(
                get_logging_config()['formatters']['console_formatter']['datefmt']
            ),
        }

        match modal:
            case None:
                pass
            case 'config':
                if data is None:
                    sharly_chess_config = SharlyChessConfig()
                    data = {
                        'console_log_level': WebContext.value_to_form_data(
                            sharly_chess_config.stored_config.console_log_level
                        ),
                        'console_color': WebContext.value_to_form_data(
                            sharly_chess_config.stored_config.console_color
                        ),
                        'console_show_date': WebContext.value_to_form_data(
                            sharly_chess_config.stored_config.console_show_date
                        ),
                        'console_show_level': WebContext.value_to_form_data(
                            sharly_chess_config.stored_config.console_show_level
                        ),
                        'experimental': WebContext.value_to_form_data(
                            sharly_chess_config.stored_config.experimental
                        ),
                        'launch_browser': WebContext.value_to_form_data(
                            sharly_chess_config.stored_config.launch_browser
                        ),
                        'federation': WebContext.value_to_form_data(
                            sharly_chess_config.stored_config.federation
                        ),
                        'locale': WebContext.value_to_form_data(
                            sharly_chess_config.stored_config.locale
                        ),
                        'default_mode': WebContext.value_to_form_data(
                            sharly_chess_config.stored_config.default_mode
                        ),
                    }
                    for plugin in plugin_manager.all_plugins:
                        data[plugin.form_key] = WebContext.value_to_form_data(
                            plugin.is_enabled
                        )
                    stored_config: StoredConfig = (
                        cls._admin_validate_config_update_data(data)
                    )
                    stored_plugins: list[StoredPlugin] = (
                        cls._admin_validate_plugins_update_data(data)
                    )
                    errors = stored_config.errors
                    for stored_plugin in stored_plugins:
                        errors |= stored_plugin.errors
                if errors is None:
                    errors = {}
                console_log_level_options: dict[str, str] = {
                    '': '-',
                } | {
                    str(console_log_level): console_log_level_str
                    for console_log_level, console_log_level_str in sharly_chess_config.console_log_levels.items()
                }
                console_log_level_options[''] = _('By default - {option}').format(
                    option=console_log_level_options[
                        str(SharlyChessConfig.default_console_log_level)
                    ]
                )
                locale_options: dict[str, str] = {
                    locale: locale_localized_name(locale) for locale in locales
                }
                plugin_form_fields_templates = (
                    plugin_manager.hook.get_event_form_fields_template() or []
                )
                context |= {
                    'console_log_level_options': console_log_level_options,
                    'locale_options': locale_options,
                    'plugin_form_fields_templates': plugin_form_fields_templates,
                    'federation_options': cls._get_federation_options(
                        SharlyChessConfig.default_federation
                    ),
                    'modal': modal,
                    'data': data,
                    'errors': errors,
                }
            case 'event':
                action: str = 'create'
                if data is None:
                    data = cls._prepare_event_modal_data(
                        action, web_context.request, None
                    )
                    stored_event: StoredEvent = cls._admin_validate_event_update_data(
                        action, web_context, None, data
                    )
                    errors = stored_event.errors
                if errors is None:
                    errors = {}

                plugin_form_fields_templates = (
                    plugin_manager.hook.get_event_form_fields_template() or []
                )
                context |= {
                    'record_illegal_moves_options': cls._get_record_illegal_moves_options(
                        SharlyChessConfig.default_record_illegal_moves_number
                    ),
                    'timer_color_texts': cls._get_timer_color_texts(
                        SharlyChessConfig.default_timer_delays
                    ),
                    'background_images_jstree_data': cls.background_images_jstree_data(
                        data['background_image']
                    ),
                    'plugin_form_fields_templates': plugin_form_fields_templates,
                    'federation_options': cls._get_federation_options(
                        default_federation=None
                    ),
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case 'database':
                databases: list[LocalSourceDatabase] = (
                    LocalSourceDatabaseManager.objects()
                )
                if data is None:
                    data = {}
                    for database in databases:
                        data |= {
                            f'{database.id}_outdate_delay': database.outdate_delay.id,
                            f'{database.id}_outdate_action': (
                                database.outdate_action.id
                            ),
                        }
                context |= {
                    'databases': databases,
                    'online_data_sources': OnlineDataSourceManager.objects(),
                    'network_connected': NetworkMonitor.connected(),
                    'outdate_delay_options': OutdatedDelayManager.options(),
                    'outdate_action_options': OutdatedActionManager.options(),
                    'modal': modal,
                    'data': data,
                    'errors': {},
                }
            case _:
                raise ValueError(f'modal=[{modal}]')
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
        path='/admin',
        name='admin',
        cache=1,
    )
    async def htmx_admin(
        self,
        request: HTMXRequest,
        admin_events_show_details: bool | None,
    ) -> Template | ClientRedirect:
        return self._admin_render(
            request,
            admin_tab=None,
            admin_events_show_details=admin_events_show_details,
        )

    @get(
        path='/admin/{admin_tab:str}',
        name='admin-tab',
        cache=1,
    )
    async def htmx_admin_tab(
        self,
        request: HTMXRequest,
        admin_tab: str,
        admin_events_show_details: bool | None,
    ) -> Template | ClientRedirect:
        return self._admin_render(
            request,
            admin_tab=admin_tab,
            admin_events_show_details=admin_events_show_details,
        )

    @get(
        path='/admin/{admin_tab:str}/event-modal/create',
        name='admin-tab-event-create-modal',
        cache=1,
    )
    async def htmx_admin_tab_event_create_modal(
        self,
        request: HTMXRequest,
        admin_tab: str,
    ) -> Template | ClientRedirect:
        return self._admin_render(
            request,
            admin_tab=admin_tab,
            modal='event',
        )

    def _admin_event_create(
        self,
        request: HTMXRequest,
        admin_tab: str,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect | Redirect:
        web_context: AdminWebContext = AdminWebContext(
            request, data=data, admin_tab=admin_tab
        )
        if web_context.error:
            return web_context.error
        stored_event: StoredEvent = self._admin_validate_event_update_data(
            'create', web_context, None, data
        )
        if stored_event.errors:
            return self._admin_render(
                request,
                admin_tab=admin_tab,
                modal='event',
                data=data,
                errors=stored_event.errors,
            )
        uniq_id: str = stored_event.uniq_id
        EventDatabase(uniq_id).create()
        with EventDatabase(uniq_id, write=True) as event_database:
            event_database.update_stored_event(stored_event, reset_permissions=False)
            event_database.commit()
        Message.success(
            request, _('Event [{uniq_id}] has been created.').format(uniq_id=uniq_id)
        )
        return Redirect(admin_event_url(request, event_uniq_id=uniq_id))

    @post(path='/admin/{admin_tab:str}/create-event', name='admin-tab-create-event')
    async def htmx_admin_tab_event_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        admin_tab: str,
    ) -> Template | ClientRedirect | Redirect:
        return self._admin_event_create(
            request,
            admin_tab=admin_tab,
            data=data,
        )

    @patch(
        path='/admin/config-update',
        name='admin-config-update',
    )
    async def htmx_admin_config_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        stored_config: StoredConfig = self._admin_validate_config_update_data(data)
        stored_plugins: list[StoredPlugin] = self._admin_validate_plugins_update_data(
            data
        )
        errors = stored_config.errors
        for plugin in stored_plugins:
            errors |= plugin.errors
        if errors:
            return self._admin_render(
                request=request,
                admin_tab='config',
                modal='config',
                data=data,
                errors=errors,
            )
        with ConfigDatabase(write=True) as config_database:
            stored_config.force_edit = False
            config_database.update_stored_config(stored_config)
            for stored_plugin in stored_plugins:
                config_database.update_stored_plugin(stored_plugin)
            config_database.commit()
        SharlyChessConfig.reload()
        plugin_manager.reload_register()
        Message.success(request, _('Sharly Chess settings have been updated.'))
        return self._admin_render(request=request, data=None, admin_tab='config')

    @patch(
        path='/admin/locale-update/{locale:str}',
        name='admin-locale-update',
    )
    async def htmx_admin_locale_update(
        self,
        request: HTMXRequest,
        locale: str,
    ) -> Template | ClientRedirect:
        sharly_chess_config: SharlyChessConfig = SharlyChessConfig()
        if locale in locales:
            stored_config: StoredConfig = sharly_chess_config.stored_config
            stored_config.locale = locale
            with ConfigDatabase(write=True) as config_database:
                config_database.update_stored_config(sharly_chess_config.stored_config)
                config_database.commit()
            sharly_chess_config.reload()
        return self._admin_render(request=request, data=None, admin_tab='config')

    @get(
        path='/admin/config-modal',
        name='admin-config-modal',
        cache=1,
    )
    async def htmx_admin_config_modal(
        self,
        request: HTMXRequest,
    ) -> Template | ClientRedirect:
        sharly_chess_config: SharlyChessConfig = SharlyChessConfig()
        return self._admin_render(
            request,
            admin_tab='config',
            modal='config',
            keep_modal_open=sharly_chess_config.force_edit,
        )

    @get(
        path='/admin/database-status-badge',
        name='admin-database-status-badge',
    )
    async def htmx_admin_status_badge(
        self,
        request: HTMXRequest,
    ) -> Template | ClientRedirect:
        source_databases: list[LocalSourceDatabase] = (
            LocalSourceDatabaseManager.objects()
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

    @get(
        path='/admin/database-modal',
        name='admin-database-modal',
    )
    async def htmx_admin_database_modal(
        self,
        request: HTMXRequest,
    ) -> Template | ClientRedirect:
        return self._admin_render(
            request,
            admin_tab=None,
            modal='database',
        )

    @patch(
        path='/admin/database-options-update',
        name='admin-database-options-update',
    )
    async def _database_options_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        source_databases: list[LocalSourceDatabase] = (
            LocalSourceDatabaseManager.objects()
        )
        with ConfigDatabase(write=True) as config_database:
            for source_database in source_databases:
                outdate_delay = (
                    WebContext.form_data_to_str(
                        data,
                        f'{source_database.id}_outdate_delay',
                    )
                    or DisabledOutdatedDelay.static_id()
                )
                outdate_action = (
                    WebContext.form_data_to_str(
                        data, f'{source_database.id}_outdate_action'
                    )
                    or NotifOutdatedAction.static_id()
                )
                config_database.update_stored_local_source_database(
                    StoredLocalSourceDatabase(
                        name=source_database.id,
                        outdate_delay=outdate_delay,
                        outdate_action=outdate_action,
                        updated_at=source_database.updated_at_timestamp,
                    )
                )
            config_database.commit()
        Message.success(
            request, _('Local source databases settings have been updated.')
        )

        # Clear the modal contents, and send an event
        return HTMXTemplate(
            template_name='common/empty_modal.html',
            re_target='#modal-wrapper',
            trigger_event='close_modal',
            after='receive',
        )

    @get(
        path='/admin/database-status/{database_id:str}',
        name='admin-database-status',
    )
    async def _database_update_status(
        self,
        request: HTMXRequest,
        database_id: str,
    ) -> Template | ClientRedirect:
        database = LocalSourceDatabaseManager.get_object(database_id)
        return HTMXTemplate(
            template_name='/admin/common/database/database_update_buttons.html',
            context={'database': database},
        )

    @post(
        path='/admin/database-update/{database_id:str}',
        name='admin-database-update',
    )
    async def _database_update(
        self,
        request: HTMXRequest,
        database_id: str,
    ) -> Reswap:
        database = LocalSourceDatabaseManager.get_object(database_id)
        database.update()
        return Reswap(content=None, method='none', status_code=HTTP_200_OK)

    @delete(
        path='/admin/database-delete/{database_id:str}',
        name='admin-database-delete',
        status_code=HTTP_200_OK,
    )
    async def _database_delete(
        self,
        request: HTMXRequest,
        database_id: str,
    ) -> Template | ClientRedirect:
        try:
            database = LocalSourceDatabaseManager.get_object(database_id)
            database.delete()
        except KeyError:
            return self.redirect_error(request, f'Unknown database [{database_id}].')
        return HTMXTemplate(
            template_name='/admin/common/database/database_update_buttons.html',
            context={'database': database},
        )

    @post(
        path='/admin/online-data-source/check/{data_source_id:str}',
        name='admin-online-data-source-check',
    )
    async def htmx_admin_data_source_check(
        self,
        request: HTMXRequest,
        data_source_id: str,
    ) -> Template | ClientRedirect:
        try:
            data_source = OnlineDataSourceManager.get_object(data_source_id)
            await data_source.reload_connection_status()
        except KeyError:
            return self.redirect_error(
                request, f'Unknown data source [{data_source_id}].'
            )
        return self._admin_render(
            request,
            admin_tab=None,
            modal='database',
        )
