import time
from datetime import datetime
from logging import Logger
from pathlib import Path
from typing import Annotated, Any

import requests
import validators
from litestar import get, post
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import HTMXTemplate, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, Redirect

from common import format_timestamp_date
from common.i18n import _, ngettext
from common.logger import get_logger
from common.papi_web_config import PapiWebConfig
from data.event import Event
from data.loader import EventLoader, ArchiveLoader
from database.access import access_driver, odbc_drivers
from database.sqlite import EventDatabase
from database.store import StoredEvent
from web.controllers.index_controller import AbstractController, WebContext
from web.messages import Message
from web.session import SessionHandler
from web.urls import admin_event_url

logger: Logger = get_logger()


class AdminWebContext(WebContext):
    """
    The basic admin web context.
    """

    def __init__(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ] | None,
            admin_tab: str | None,
    ):
        super().__init__(request, data=data)
        self.admin_tab: str | None = admin_tab
        if self.error:
            return
        self.check_admin_tab()

    def check_admin_tab(self):
        if self.admin_tab not in [None, 'config', 'passed_events', 'current_events', 'coming_events', 'archives', ]:
            self._redirect_error(f'Invalid value [{self.admin_tab}] for parameter [admin_tab]')

    @property
    def background_image(self) -> str | None:
        if self.admin_tab in ['archives', 'config', ]:
            return PapiWebConfig.default_background_image
        else:
            return None

    @property
    def background_color(self) -> str:
        return PapiWebConfig.admin_background_color

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_tab': self.admin_tab,
        }


class AbstractAdminController(AbstractController):

    @staticmethod
    def _get_record_illegal_moves_options(default: int | None, ) -> dict[str, str]:
        options: dict[str, str] = {
            '': '',
            '0': _('No recording'),
        } | {
            str(i): ngettext('{num} illegal move max', '{num} illegal moves max', i).format(num=i)
            for i in range (1, 4)
        }
        options[''] = _('By default - {option}').format(option=options[str(default)])
        return options

    @staticmethod
    def _get_timer_color_texts(delays: dict[int, int]) -> dict[int, str]:
        return {
            1: _(
                'Colour #1 is used until {delay_1} minutes before the start of the rounds (delay #1), the color then changes gradually until colour #2 ({delay_2} minutes before the start of the rounds).'
            ).format(delay_1=delays[1], delay_2=delays[2]),
            2: _(
                'Colour #2 is used {delay_2} minutes before the start of the rounds (delay #2), the color then changes gradually until colour #3 (at the start of the rounds).'
            ).format(delay_2=delays[2]),
            3: _(
                'Colour #3 is used from the start of the rounds and for {delay_3} minutes after (delay #3).'
            ).format(delay_3=delays[3]),
        }

    @staticmethod
    def _get_screen_type_options(family_screens_only: bool) -> dict[str, str]:
        options: dict[str, str] = {
            '': '-',
            'input': _('Results entry'),
            'boards': _('Pairings by board'),
            'players': _('Pairings by player'),
        }
        if not family_screens_only:
            options['results'] = _('Last results')
            options['image'] = _('Image')
        return options

    @staticmethod
    def _get_timer_options(event: Event) -> dict[str, str]:
        options: dict[str, str] = {
            '': _('Use no timer') if event.timers_by_id else _('No timer defined'),
        }
        for timer in event.timers_by_id.values():
            options[str(timer.id)] = _('Timer {timer_uniq_id}').format(timer_uniq_id=timer.uniq_id)
        return options

    @staticmethod
    def _get_input_exit_button_options() -> dict[str, str]:
        options: dict[str, str] = {
            '': '-',
            'on': _('Display the exit button'),
            'off': _('Hide the exit button'),
        }
        options[''] = _('By default - {option}').format(
            option=options["on" if PapiWebConfig.default_input_exit_button else "off"])
        return options

    @staticmethod
    def _get_players_show_unpaired_options() -> dict[str, str]:
        options: dict[str, str] = {
            '': '-',
            'off': _('Display only paired players'),
            'on': _('Display all the players, paired and unpaired'),
        }
        options[''] = _('By default - {option}').format(
            option=options["on" if PapiWebConfig.default_players_show_unpaired else "off"])
        return options


class AbstractIndexAdminController(AbstractAdminController):
    """ An abstract class inherited by all the admin controllers."""

    @staticmethod
    def set_admin_columns(request: HTMXRequest, admin_columns: int | None):
        if admin_columns:
            SessionHandler.set_session_admin_columns(request, admin_columns)

    @staticmethod
    def _admin_validate_record_illegal_moves_update_data(
            data: dict[str, str] | None,
            errors: dict[str, str],
    ) -> int | None:
        field: str = 'record_illegal_moves'
        record_illegal_moves: int | None
        try:
            record_illegal_moves = WebContext.form_data_to_int(data, field)
            assert record_illegal_moves is None or 0 <= record_illegal_moves <= 3
        except (ValueError, AssertionError):
            record_illegal_moves = None
            errors['record_illegal_moves'] = _('Invalid value [{value}].').format(value=data[field])
        return record_illegal_moves

    @staticmethod
    def _admin_validate_rules_update_data(
            data: dict[str, str] | None,
            errors: dict[str, str],
    ) -> str | None:
        field: str = 'rules'
        rules: str | None = WebContext.form_data_to_str(data, field)
        if rules:
            if validators.url(rules):
                try:
                    response = requests.get(rules)
                    if response.status_code != 200:
                        errors[field] = _(
                            'URL [{url}] responded code [{code}].').format(url=rules, code=response.status_code)
                except requests.ConnectionError as ce:
                    errors[field] = _(
                        'URL [{url}] did not respond (error: [{error}]).').format(url=rules, error=str(ce))
            else:
                if rules.find('..') != -1:
                    errors[field] = _('Incorrect path [{path}].').format(path=rules)
                    data[field] = ''
                else:
                    file: Path = Path(rules)
                    if not file.exists() or not file.is_file():
                        errors[field] = _('File [{file}] not found.').format(file=rules)
                    elif file.suffix.lower() != '.pdf':
                        errors[field] = _('Wrong file extension [{ext}] ([pdf] expected).').format(ext=file.suffix)
        return rules

    @staticmethod
    def _admin_validate_background_color_update_data(
            data: dict[str, str] | None,
            errors: dict[str, str],
    ) -> str | None:
        field: str = 'background_color'
        background_color: str | None = None
        color_checkbox = WebContext.form_data_to_bool(data, field + '_checkbox')
        if not color_checkbox:
            try:
                background_color = WebContext.form_data_to_rgb(data, field)
            except ValueError:
                errors[field] = _('Invalid color [{color}] ([#RRGGBB] expected).').format(color={data[field]})
        return background_color

    @classmethod
    def _admin_validate_event_update_data(
            cls,
            action: str,
            request: HTMXRequest,
            admin_event: Event | None,
            data: dict[str, str] | None = None,
    ) -> StoredEvent:
        if data is None:
            data = {}
        errors: dict[str, str] = {}
        uniq_id: str | None = WebContext.form_data_to_str(data, 'uniq_id')
        if action == 'delete':
            if not uniq_id:
                errors['uniq_id'] = _('Please enter the event ID.')
            elif uniq_id != admin_event.uniq_id:
                errors['uniq_id'] = _('event ID does not match.')
        else:
            if not uniq_id:
                errors['uniq_id'] = _('Please enter the event ID.')
            elif uniq_id.find('/') != -1:
                errors['uniq_id'] = _('Character [{char}] is not allowed.').format(char='/')
            else:
                event_uniq_ids: list[str] = EventLoader.get(request=request).event_uniq_ids
                match action:
                    case 'clone' | 'create':
                        if uniq_id in event_uniq_ids:
                            errors['uniq_id'] = _('Event [{uniq_id}] already exists.').format(uniq_id=uniq_id)
                    case 'update':
                        if uniq_id != admin_event.uniq_id and uniq_id in event_uniq_ids:
                            errors['uniq_id'] = _('Event [{uniq_id}] already exists.').format(uniq_id=uniq_id)
                    case _:
                        raise ValueError(f'action=[{action}]')
        name: str | None = None
        start: float | None = None
        stop: float | None = None
        public: bool | None = None
        path: str | None = None
        hide_background_image: bool | None = None
        background_image: str | None = None
        background_color: str | None = None
        update_password: str | None = None
        record_illegal_moves: int | None = None
        rules: str | None = None
        timer_colors: dict[int, str | None] = {i: None for i in range(1, 4)}
        timer_delays: dict[int, int | None] = {i: None for i in range(1, 4)}
        message_text: str | None = None
        message_color: str | None = None
        message_background_color: str | None = None
        match action:
            case 'clone' | 'update' | 'create':
                name: str | None = WebContext.form_data_to_str(data, 'name')
                if not name:
                    errors['name'] = _('Please enter the name of the event.')
                start_str: str | None = WebContext.form_data_to_str(data, 'start')
                if not start_str:
                    errors['start'] = _('Please enter the start date of the event.')
                else:
                    start = time.mktime(datetime.strptime(start_str, '%Y-%m-%dT%H:%M').timetuple())
                stop_str: str | None = WebContext.form_data_to_str(data, 'stop')
                if not stop_str:
                    errors['stop'] = _('Please enter the end date of the event.')
                else:
                    stop = time.mktime(datetime.strptime(stop_str, '%Y-%m-%dT%H:%M').timetuple())
                if 'start' not in errors and 'stop' not in errors and start > stop:
                    errors['stop'] = _('Please enter a date after the start date.')
                public = WebContext.form_data_to_bool(data, 'public')
                path: str | None = WebContext.form_data_to_str(data, 'path')
                update_password = WebContext.form_data_to_str(data, 'update_password')
                field = 'background_image'
                hide_background_image = WebContext.form_data_to_bool(data, field + '_checkbox')
                if not hide_background_image:
                    if background_image := WebContext.form_data_to_str(data, field, ''):
                        if validators.url(background_image):
                            try:
                                response = requests.get(background_image)
                                if response.status_code != 200:
                                    errors[field] = _(
                                        'URL [{url}] responded code [{code}].').format(
                                        url=background_image, code=response.status_code)
                            except requests.ConnectionError as ce:
                                errors[field] = _(
                                    'URL [{url}] did not respond (error: [{error}]).').format(
                                    url=background_image, error=str(ce))
                        elif Path(background_image).exists():
                            errors[field] = _('Please enter a URL or select an image on the right hand side.')
                        else:
                            background_image = background_image.strip('/')
                            if background_image.find('..') != -1:
                                errors[field] = _('Incorrect path [{path}].').format(path=background_image)
                                data[field] = ''
                            elif not (PapiWebConfig.custom_path / background_image).exists() \
                                    and not (PapiWebConfig.embedded_custom_path / background_image).exists():
                                errors[field] = _('File [{file}] not found.').format(file=background_image)
                background_color = cls._admin_validate_background_color_update_data(data, errors)
                record_illegal_moves = cls._admin_validate_record_illegal_moves_update_data(data, errors)
                rules = cls._admin_validate_rules_update_data(data, errors)
                for i in range(1, 4):
                    field: str = f'color_{i}'
                    if not WebContext.form_data_to_bool(data, field + '_checkbox'):
                        try:
                            timer_colors[i] = WebContext.form_data_to_rgb(data, field)
                        except ValueError:
                            errors[field] = _('Invalid color [{color}] ([#RRGGBB] expected).').format(
                                color={data[field]})
                    field: str = f'delay_{i}'
                    try:
                        timer_delays[i] = WebContext.form_data_to_int(data, field, minimum=1)
                    except ValueError:
                        errors[field] = _('Invalid delay [{delay}] (positive integer expected).').format(
                            delay=data[field])
                field: str = 'message_text'
                message_text = WebContext.form_data_to_str(data, field)
                field: str = 'message_color'
                if not WebContext.form_data_to_bool(data, field + '_checkbox'):
                    try:
                        message_color = WebContext.form_data_to_rgb(data, field)
                    except ValueError:
                        errors[field] = _('Invalid color [{color}] ([#RRGGBB] expected).').format(color={data[field]})
                field: str = 'message_background_color'
                if not WebContext.form_data_to_bool(data, field + '_checkbox'):
                    try:
                        message_background_color = WebContext.form_data_to_rgb(data, field)
                    except ValueError:
                        errors[field] = _('Invalid color [{color}] ([#RRGGBB] expected).').format(color={data[field]})
                pass
            case 'delete':
                pass
            case _:
                raise ValueError(f'action=[{action}]')
        return StoredEvent(
            uniq_id=uniq_id,
            name=name,
            start=start,
            stop=stop,
            public=public,
            path=path,
            hide_background_image=hide_background_image,
            background_image=background_image,
            background_color=background_color,
            update_password=update_password,
            record_illegal_moves=record_illegal_moves,
            rules=rules,
            timer_colors=timer_colors,
            timer_delays=timer_delays,
            message_text=message_text,
            message_color=message_color,
            message_background_color=message_background_color,
            errors=errors,
        )

    @staticmethod
    def background_images_jstree_data(background_image: str) -> list[dict[str, Any]]:
        dirs: list[str] = []
        files: list[str] = []
        for custom_path in [PapiWebConfig.embedded_custom_path, PapiWebConfig.custom_path, ]:
            for item in custom_path.rglob('*'):
                item_str = str(item).replace(str(custom_path), '').replace('\\', '/').lstrip('/')
                if item.is_dir():
                    if item_str not in dirs:
                        dirs.append(item_str)
                else:
                    if item_str not in files:
                        files.append(item_str)
        dir_nodes: list[dict[str, str]] = [{
            'id': d or '#',
            'parent': '/'.join(d.split('/')[:-1]) or '#',
            'text': f' {d.split("/")[-1]}',
            'state': {},
            'icon': 'bi-folder',
        } for d in dirs]
        file_nodes: list[dict[str, str]] = [{
            'id': f or '#',
            'parent': '/'.join(f.split('/')[:-1]) or '#',
            'text': f.split('/')[-1],
            'state': {
                'selected': background_image == f,
            },
            'icon': 'bi-card-image',
            'a_attr': {
                'onclick': f'$("#background-image").val("{f}"); '
                           f'$.ajax({{'
                           f'    url: "/background",'
                           f'    type: "GET",'
                           f'    data: {{ "image": "{f}", "color": $("#background-color").val() }},'
                           f'    success: function(data) {{'
                           f'        $("#background-image-test").css("background-image", data["url"]);'
                           f'    }},'
                           f'    error: function(jqXHR, exception) {{'
                           f'        console.log('
                           f'            "Changing background failed: status_code=" + jqXHR.status '
                           f'            + ", exception=" + exception + ", response=" + jqXHR.responseText'
                           f'        );'
                           f'    }},'
                           f'}});',
            }
        } for f in files]
        return file_nodes + dir_nodes

    @classmethod
    def _prepare_event_modal_data(
            cls,
            action: str,
            request: HTMXRequest,
            admin_event: Event | None,
    ) -> dict[str, str]:
        uniq_id: str | None = None
        name: str | None = None
        match action:
            case 'update':
                name = admin_event.stored_event.name
                uniq_id = admin_event.stored_event.uniq_id
            case 'clone':
                name = EventLoader.get(request).get_unused_event_name(admin_event.stored_event.name)
                uniq_id = EventLoader.get(request).get_unused_event_uniq_id(admin_event.stored_event.uniq_id)
            case 'create':
                name = EventLoader.get(request).get_unused_event_name(_('New event'))
                uniq_id = EventLoader.get(request).get_unused_event_uniq_id(_('event'))
            case 'delete':
                pass
            case _:
                raise ValueError(f'action=[{action}]')
        start: float | None = None
        stop: float | None = None
        match action:
            case 'update' | 'clone':
                start = admin_event.stored_event.start
                stop = admin_event.stored_event.stop
            case 'create':
                today_str: str = format_timestamp_date()
                start = time.mktime(datetime.strptime(
                    f'{today_str} 00:00', '%Y-%m-%d %H:%M').timetuple())
                stop = time.mktime(datetime.strptime(
                    f'{today_str} 23:59', '%Y-%m-%d %H:%M').timetuple())
            case 'delete':
                pass
            case _:
                raise ValueError(f'action=[{action}]')
        public: bool | None = None
        hide_background_image: bool | None = None
        background_image: str | None = None
        background_color: str | None = None
        path: str | None = None
        update_password: str | None = None
        record_illegal_moves: int | None = None
        rules: str | None = None
        colors: dict[int, str | None] = {i: None for i in range(1, 4)}
        delays: dict[int, int | None] = {i: None for i in range(1, 4)}
        message_text: str | None = None
        message_color: str | None = None
        message_background_color: str | None = None
        match action:
            case 'update' | 'clone':
                public = admin_event.stored_event.public
                hide_background_image = admin_event.stored_event.hide_background_image
                background_image = admin_event.stored_event.background_image
                background_color = admin_event.stored_event.background_color
                path = admin_event.stored_event.path
                update_password = admin_event.stored_event.update_password
                record_illegal_moves = admin_event.stored_event.record_illegal_moves
                rules = admin_event.stored_event.rules
                colors = admin_event.stored_event.timer_colors
                delays = admin_event.stored_event.timer_delays
                message_text = admin_event.stored_event.message_text
                message_color = admin_event.message_color
                message_background_color = admin_event.message_background_color
            case 'create':
                public = False
                hide_background_image = PapiWebConfig.default_hide_background_image
            case 'delete':
                pass
            case _:
                raise ValueError(f'action=[{action}]')
        return {
           'uniq_id': WebContext.value_to_form_data(uniq_id),
           'name': WebContext.value_to_form_data(name),
           'public': WebContext.value_to_form_data(public),
           'start': WebContext.value_to_datetime_form_data(start),
           'stop': WebContext.value_to_datetime_form_data(stop),
           'background_image_checkbox': WebContext.value_to_form_data(hide_background_image),
           'background_image': WebContext.value_to_form_data(background_image),
           'background_color': WebContext.value_to_form_data(background_color),
           'background_color_checkbox': WebContext.value_to_form_data(background_color is None),
           'path': WebContext.value_to_form_data(path),
           'update_password': WebContext.value_to_form_data(update_password),
           'record_illegal_moves': WebContext.value_to_form_data(record_illegal_moves),
           'rules': WebContext.value_to_form_data(rules),
           'message_text': WebContext.value_to_form_data(message_text),
           'message_color_checkbox': WebContext.value_to_form_data(message_color is None),
           'message_color': WebContext.value_to_form_data(message_color),
           'message_background_color_checkbox': WebContext.value_to_form_data(
               message_background_color is None),
           'message_background_color': WebContext.value_to_form_data(message_background_color),
       } | {
           f'color_{i}': WebContext.value_to_form_data(colors[i]) for i in range(1, 4)
       } | {
           f'color_{i}_checkbox': WebContext.value_to_form_data(colors[i] is None) for i in
           range(1, 4)
       } | {
           f'delay_{i}': WebContext.value_to_form_data(delays[i]) for i in range(1, 4)
       }

    @classmethod
    def _admin_render(
            cls,
            web_context: AdminWebContext,
            modal: str | None = None,
            data: dict[str, str] | None = None,
            errors:  dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        event_loader: EventLoader = EventLoader.get(request=web_context.request)
        archive_loader: ArchiveLoader = ArchiveLoader.get(request=web_context.request)
        nav_tabs: dict[str, dict[str, Any]] = {
            'current_events': {
                'title': _('Current events ({num})').format(num=len(event_loader.current_events) or '-'),
                'template': 'admin_events.html',
                'events': event_loader.current_events,
                'disabled': not event_loader.current_events,
                'empty_str': _('No current events.'),
                'icon_class': 'bi-calendar',
            },
            'coming_events': {
                'title': _('Upcoming events ({num})').format(num=len(event_loader.coming_events) or '-'),
                'template': 'admin_events.html',
                'events': event_loader.coming_events,
                'disabled': not event_loader.coming_events,
                'empty_str': _('No upcoming events.'),
                'icon_class': 'bi-calendar-check',
            },
            'passed_events': {
                'title': _('Passed events ({num})').format(num=len(event_loader.passed_events) or '-'),
                'template': 'admin_events.html',
                'events': event_loader.passed_events,
                'disabled': not event_loader.passed_events,
                'empty_str': _('No passed events.'),
                'icon_class': 'bi-calendar-minus',
            },
            'archives': {
                'title': _('Archived events ({num})').format(num=len(archive_loader.archives_sorted_by_date) or '-'),
                'template': 'admin_archives.html',
                'archives': archive_loader.archives_sorted_by_date,
                'disabled': not archive_loader.archives_sorted_by_date,
                'empty_str': _('No archived events.'),
                'icon_class': 'bi-archive-fill',
            },
            'config': {
                'title': _('Papi-web configuration'),
                'template': 'admin_config.html',
                'icon_class': 'bi-gear-fill',
                'disabled': False,
            },
        }
        if not web_context.admin_tab or nav_tabs[web_context.admin_tab]['disabled']:
            web_context.admin_tab = list(nav_tabs.keys())[0]
        for nav_index in range(len(nav_tabs)):
            if web_context.admin_tab == list(nav_tabs.keys())[nav_index] \
                    and nav_tabs[web_context.admin_tab]['disabled']:
                web_context.admin_tab = list(nav_tabs.keys())[(nav_index + 1) % len(nav_tabs)]
        context = web_context.template_context | {
            'odbc_drivers': odbc_drivers(),
            'access_driver': access_driver(),
            'messages': Message.messages(web_context.request),
            'nav_tabs': nav_tabs,
            'admin_columns': SessionHandler.get_session_admin_columns(web_context.request),
        }
        match modal:
            case None:
                pass
            case 'event':
                if data is None:
                    data = cls._prepare_event_modal_data('create', web_context.request, None)
                    stored_event: StoredEvent = cls._admin_validate_event_update_data('create', web_context.request, None, data)
                    errors = stored_event.errors
                if errors is None:
                    errors = {}
                context |= {
                    'record_illegal_moves_options': cls._get_record_illegal_moves_options(
                        PapiWebConfig.default_record_illegal_moves_number),
                    'timer_color_texts': cls._get_timer_color_texts(PapiWebConfig.default_timer_delays),
                    'background_images_jstree_data': cls.background_images_jstree_data(data['background_image']),
                    'modal': 'event',
                    'action': 'create',
                    'data': data,
                    'errors': errors,
                }
            case _:
                raise ValueError(f'modal=[{modal}]')
        return HTMXTemplate(
            template_name="admin_index.html",
            context=context)


class IndexAdminController(AbstractIndexAdminController):

    @classmethod
    def _admin(
            cls, request: HTMXRequest,
            admin_tab: str | None,
            admin_columns: int | None = None,
            locale: str | None = None,
            modal: str | None = None,
            data: dict[str, str] | None = None,
            errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        cls.set_locale(request, locale)
        cls.set_admin_columns(request, admin_columns)
        web_context: AdminWebContext = AdminWebContext(request, data=None, admin_tab=admin_tab)
        if web_context.error:
            return web_context.error
        return cls._admin_render(web_context, modal=modal, data=data, errors=errors)

    @get(
        path='/admin',
        name='admin',
        cache=1,
    )
    async def htmx_admin(
            self, request: HTMXRequest,
            admin_columns: int | None,
            locale: str | None,
    ) -> Template | ClientRedirect:
        return self._admin(request, admin_tab=None, admin_columns=admin_columns, locale=locale, )

    @get(
        path='/admin/{admin_tab:str}',
        name='admin-tab',
        cache=1,
    )
    async def htmx_admin_tab(
            self, request: HTMXRequest,
            admin_tab: str,
            admin_columns: int | None,
            locale: str | None,
    ) -> Template | ClientRedirect:
        return self._admin(request, admin_tab=admin_tab, admin_columns=admin_columns, locale=locale, )

    @get(
        path='/admin/{admin_tab:str}/event-modal/create',
        name='admin-tab-event-create-modal',
        cache=1,
    )
    async def htmx_admin_tab_event_create_modal(
            self, request: HTMXRequest,
            admin_tab: str,
    ) -> Template | ClientRedirect:
        return self._admin(request, admin_tab=admin_tab, modal='event', )

    def _admin_event_create(
            self, request: HTMXRequest,
            admin_tab: str,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
    ) -> Template | ClientRedirect | Redirect:
        web_context: AdminWebContext = AdminWebContext(request, data=data, admin_tab=admin_tab)
        if web_context.error:
            return web_context.error
        stored_event: StoredEvent = self._admin_validate_event_update_data('create', request, None, data)
        if stored_event.errors:
            return self._admin(
                request, admin_tab=admin_tab, modal='event', data=data, errors=stored_event.errors)
        uniq_id: str = stored_event.uniq_id
        EventDatabase(uniq_id).create()
        with EventDatabase(uniq_id, write=True) as event_database:
            event_database.update_stored_event(stored_event)
            event_database.commit()
        Message.success(request, _('Event [{uniq_id}] has been created.').format(uniq_id=uniq_id))
        return Redirect(admin_event_url(request, event_uniq_id=uniq_id))

    @post(
        path='/admin/{admin_tab:str}/create-event',
        name='admin-tab-create-event'
    )
    async def htmx_admin_tab_event_create(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            admin_tab: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_create(request, admin_tab=admin_tab, data=data, )
