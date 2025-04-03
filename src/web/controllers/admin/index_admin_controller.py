from logging import Logger
from typing import Annotated, Any

from data.loader import ArchiveLoader, EventLoader
from data.player import Federation
from database.access.access_database import access_driver, odbc_drivers

from litestar import get, post, patch, delete
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import ClientRedirect, HTMXTemplate
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, Redirect
from litestar.status_codes import HTTP_200_OK

from common.i18n import (
    _,
    DEFAULT_LOCALE,
    EXPERIMENTAL_FEATURES,
    locale_localized_name,
    trusted_locales,
    untrusted_locales,
)
from common.logger import get_logger
from common.papi_web_config import PapiWebConfig
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.config.config_store import StoredConfig, StoredPlugin, StoredLocalSourceDatabase
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredEvent
from database.sqlite.local_source_database import (
    LocalSourceDatabaseManager,
    LocalSourceDatabase,
    DisabledOutdateDelay,
    NotifOutdateAction,
    OutdateDelayManager,
    OutdateActionManager,
)
from plugins.manager import plugin_manager
from web.controllers.admin.base_admin_controller import AdminWebContext, BaseAdminController
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
        papi_web_config: PapiWebConfig = PapiWebConfig()
        if data is None:
            data = {}
        errors: dict[str, str] = {}
        log_level: int | None = WebContext.form_data_to_int(data, field := 'log_level')
        if log_level and log_level not in papi_web_config.log_levels:
            errors[field] = _('Invalid log level [{log_level}].').format(log_level=log_level)
            data[field] = ''
        launch_browser: bool | None = WebContext.form_data_to_bool(data, 'launch_browser')
        federation_name: str | None = WebContext.form_data_to_str(data, field := 'federation')
        federation: Federation | None = None
        if federation_name:
            if federation_name not in papi_web_config.federations:
                errors[field] = _('Invalid federation [{federation}].').format(federation=federation_name)
                data[field] = ''
            else:
                federation = Federation(federation_name)
        locale: str | None = WebContext.form_data_to_str(data, field := 'locale')
        if locale and locale not in papi_web_config.locales:
            errors[field] = _('Invalid locale [{locale}].').format(locale=locale)
            data[field] = ''
        return StoredConfig(
            version=str(papi_web_config.version),
            log_level=log_level,
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
                    is_enabled=WebContext.form_data_to_bool(
                        data, plugin.form_key, False
                    ),
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
            
        papi_web_config: PapiWebConfig = PapiWebConfig()
        event_loader: EventLoader = EventLoader.get(request=web_context.request)
        archive_loader: ArchiveLoader = ArchiveLoader.get(request=web_context.request)
        nav_tabs: dict[str, dict[str, Any]] = {
            'current_events': {
                'title': _('Current events ({num})').format(
                    num=len(event_loader.current_events) or '-'
                ),
                'template': 'index/events_tab.html',
                'events': event_loader.current_events,
                'disabled': not event_loader.current_events,
                'empty_str': _('No current events.'),
                'icon_class': 'bi-calendar',
            },
            'coming_events': {
                'title': _('Upcoming events ({num})').format(
                    num=len(event_loader.coming_events) or '-'
                ),
                'template': 'index/events_tab.html',
                'events': event_loader.coming_events,
                'disabled': not event_loader.coming_events,
                'empty_str': _('No upcoming events.'),
                'icon_class': 'bi-calendar-check',
            },
            'passed_events': {
                'title': _('Passed events ({num})').format(
                    num=len(event_loader.passed_events) or '-'
                ),
                'template': 'index/events_tab.html',
                'events': event_loader.passed_events,
                'disabled': not event_loader.passed_events,
                'empty_str': _('No passed events.'),
                'icon_class': 'bi-calendar-minus',
            },
            'archives': {
                'title': _('Archived events ({num})').format(
                    num=len(archive_loader.archives_sorted_by_date) or '-'
                ),
                'template': 'index/archives_tab.html',
                'archives': archive_loader.archives_sorted_by_date,
                'disabled': not archive_loader.archives_sorted_by_date,
                'empty_str': _('No archived events.'),
                'icon_class': 'bi-archive',
            },
            'config': {
                'title': _('Papi-web settings'),
                'template': 'index/config_tab.html',
                'icon_class': 'bi-gear',
                'disabled': False,
            },
        }
        if papi_web_config.force_edit:
            web_context.admin_tab = 'config'
        if not modal and (not web_context.admin_tab or nav_tabs[web_context.admin_tab]['disabled']):
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
            'row_cycler': cls.get_cycler(['odd', 'even'])
        }

        match modal:
            case None:
                pass
            case 'config':
                if data is None:
                    papi_web_config: PapiWebConfig = PapiWebConfig()
                    data = {
                        'log_level': WebContext.value_to_form_data(papi_web_config.stored_config.log_level),
                        'launch_browser': WebContext.value_to_form_data(papi_web_config.stored_config.launch_browser),
                        'federation': WebContext.value_to_form_data(papi_web_config.stored_config.federation),
                        'locale': WebContext.value_to_form_data(papi_web_config.stored_config.locale),
                    }
                    for plugin in plugin_manager.all_plugins:
                        data[plugin.form_key] = (
                            WebContext.value_to_form_data(plugin.is_enabled)
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
                log_level_options: dict[str, str] = {
                    '': '-',
                } | {
                    str(log_level): log_level_str
                    for log_level, log_level_str in papi_web_config.log_levels.items()
                }
                log_level_options[''] = _('By default - {option}').format(
                    option=log_level_options[str(PapiWebConfig.default_log_level)]
                )
                launch_browser_options: dict[str, str] = {
                    '': '-',
                    'on': _('Automatically launch a browser when starting the server'),
                    'off': _('Do nothing'),
                }
                launch_browser_options[''] = _('By default - {option}').format(
                    option=launch_browser_options['on' if PapiWebConfig.default_launch_browser else 'off']
                )
                locale_options: dict[str, str] = {
                    '': '-',
                } | {
                    locale: locale_localized_name(locale)
                    for locale in trusted_locales
                }
                if EXPERIMENTAL_FEATURES:
                    locale_options |= {
                        locale: locale_localized_name(locale)
                        for locale in untrusted_locales
                    }
                locale_options[''] = _('By default - {option}').format(
                    option=locale_options[DEFAULT_LOCALE]
                )
                plugin_form_fields_templates = plugin_manager.hook.get_event_form_fields_template() or []
                context |= {
                    'log_level_options': log_level_options,
                    'launch_browser_options': launch_browser_options,
                    'locale_options': locale_options,
                    'plugin_form_fields_templates': plugin_form_fields_templates,
                    'federation_options': cls._get_federation_options(PapiWebConfig.default_federation),
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
                        action, web_context.request, None, data
                    )
                    errors = stored_event.errors
                if errors is None:
                    errors = {}

                plugin_form_fields_templates = plugin_manager.hook.get_event_form_fields_template() or []
                context |= {
                    'record_illegal_moves_options': cls._get_record_illegal_moves_options(
                        PapiWebConfig.default_record_illegal_moves_number
                    ),
                    'timer_color_texts': cls._get_timer_color_texts(
                        PapiWebConfig.default_timer_delays
                    ),
                    'background_images_jstree_data': cls.background_images_jstree_data(
                        data['background_image']
                    ),
                    'plugin_form_fields_templates': plugin_form_fields_templates,
                    'federation_options': cls._get_federation_options(
                        papi_web_config.stored_config.federation
                        or PapiWebConfig.default_federation
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
                            f'{database.id}_outdate_delay': (
                                database.outdate_delay.id
                            ),
                            f'{database.id}_outdate_action': (
                                database.outdate_action.id
                            )
                        }
                context |= {
                    'databases': databases,
                    'outdate_delay_options': OutdateDelayManager.options(),
                    'outdate_action_options': OutdateActionManager.options(),
                    'modal': modal,
                    'data': data,
                    'errors': {},
                }
            case _:
                raise ValueError(f'modal=[{modal}]')
        if "modal" in context:
            return HTMXTemplate(
                template_name='admin/modals.html',
                context=context,
                re_target='#modal-wrapper',
                trigger_event="modal_opened",
                after="settle"
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
            'create', request, None, data
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
            event_database.update_stored_event(stored_event)
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
    ) -> Template | ClientRedirect:
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
        stored_config: StoredConfig = (
            self._admin_validate_config_update_data(data)
        )
        stored_plugins: list[StoredPlugin] = (
            self._admin_validate_plugins_update_data(data)
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
        PapiWebConfig().reload()
        plugin_manager.reload_register()
        Message.success(request, _('Papi-web settings has been updated.'))
        return self._admin_render(
            request=request,
            data=None,
            admin_tab='config'
        )

    @patch(
        path='/admin/locale-update/{locale:str}',
        name='admin-locale-update',
    )
    async def htmx_admin_locale_update(
        self,
        request: HTMXRequest,
        locale: str,
    ) -> Template | ClientRedirect:
        papi_web_config: PapiWebConfig = PapiWebConfig()
        if locale in papi_web_config.locales:
            stored_config: StoredConfig = papi_web_config.stored_config
            stored_config.locale = locale
            with ConfigDatabase(write=True) as config_database:
                config_database.update_stored_config(papi_web_config.stored_config)
                config_database.commit()
            papi_web_config.reload()
        return self._admin_render(
            request=request,
            data=None,
            admin_tab='config'
        )

    @get(
        path='/admin/config-modal',
        name='admin-config-modal',
        cache=1,
    )
    async def htmx_admin_config_modal(
        self,
        request: HTMXRequest,
    ) -> Template | ClientRedirect:
        return self._admin_render(
            request,
            admin_tab='config',
            modal='config',
        )

    @get(
        path='/admin/database-status-badge',
        name='admin-database-status-badge',
    )
    async def htmx_admin_status(
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
                        request, _(
                            'Database [{database}] successfully updated.'
                        ).format(database=database.name)
                    )
                else:
                    Message.error(
                        request, _(
                            'Error when updating database [{database}].'
                        ).format(database=database.name)
                    )
                database.__class__.update_status = None

        if any([database.is_updating for database in source_databases]):
            template_name = '/admin/common/database/updating_badge.html'
        elif any([database.outdated_warning for database in source_databases]):
            template_name = '/admin/common/database/out_of_date_badge.html'
        else:
            template_name = '/admin/common/database/settings_badge.html'
        return HTMXTemplate(
            template_name=template_name
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
                outdate_delay = WebContext.form_data_to_str(
                    data, f'{source_database.id}_outdate_delay',
                ) or DisabledOutdateDelay.static_id()
                outdate_action = WebContext.form_data_to_str(
                    data, f'{source_database.id}_outdate_action'
                ) or NotifOutdateAction.static_id()
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
            trigger_event="close_modal",
            after="receive",
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
            context={"database": database}
        )

    @post(
        path='/admin/database-update/{database_id:str}',
        name='admin-database-update',
    )
    async def _database_update(
        self,
        request: HTMXRequest,
        database_id: str,
    ) -> Template | ClientRedirect:
        database = LocalSourceDatabaseManager.get_object(database_id)
        database.update()
        return HTMXTemplate(
            template_name='/admin/common/database/database_update_buttons.html',
            trigger_event="database-update-launched",
            after="receive",
            context={"database": database}
        )

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
        database = LocalSourceDatabaseManager.get_object(database_id)
        database.delete()
        return HTMXTemplate(
            template_name='/admin/common/database/database_update_buttons.html',
            context={"database": database}
        )
