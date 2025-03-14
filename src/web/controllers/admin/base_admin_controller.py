import time
from datetime import datetime
from logging import Logger
from pathlib import Path
from typing import Annotated, Any

import requests
import validators
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import HTMXTemplate, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template

from common import format_timestamp_date, EXPERIMENTAL_FEATURES, REQUEST_TIMEOUT
from common.i18n import _, ngettext, locale_localized_name, trusted_locales, untrusted_locales, DEFAULT_LOCALE
from common.logger import get_logger
from common.papi_web_config import PapiWebConfig
from data.event import Event
from data.loader import EventLoader, ArchiveLoader
from data.player import Federation
from data.tie_break import PapiTieBreak
from data.util import Result
from database.access.access_database import access_driver, odbc_drivers
from database.sqlite.config.config_store import StoredConfig
from database.sqlite.event.event_store import StoredEvent
from plugins.manager import plugin_manager
from web.controllers.base_controller import BaseController, WebContext
from web.messages import Message
from web.session import SessionHandler

logger: Logger = get_logger()


class AdminWebContext(WebContext):
    """
    The basic admin web context.
    """

    def __init__(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str] | None,
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        admin_tab: str | None,
    ):
        super().__init__(request, data=data)
        self.admin_tab: str | None = admin_tab
        if self.error:
            return
        self.check_admin_tab()

    def check_admin_tab(self):
        if self.admin_tab not in [
            None,
            'config',
            'passed_events',
            'current_events',
            'coming_events',
            'archives',
        ]:
            self._redirect_error(
                f'Invalid value [{self.admin_tab}] for parameter [admin_tab]'
            )

    @property
    def background_image(self) -> str | None:
        return None

    @property
    def background_color(self) -> str:
        return PapiWebConfig.admin_background_color

    @property
    def theme(self) -> str:
        return 'dark'

    @property
    def template_context(self) -> dict[str, Any]:
        per_plugin_context = plugin_manager.hook.get_base_admin_context()
        plugin_context =  {key: value for context in per_plugin_context for key, value in context.items()}

        return super().template_context | {
            'admin_tab': self.admin_tab,
        } | plugin_context


class BaseAdminController(BaseController):
    """An base class inherited by all the admin controllers."""

    @staticmethod
    def _get_record_illegal_moves_options(
        default: int | None,
    ) -> dict[str, str]:
        options: dict[str, str] = {
            '': '',
            WebContext.value_to_form_data(0): _('No recording'),
        } | {
            WebContext.value_to_form_data(i): ngettext(
                '{num} illegal move max', '{num} illegal moves max', i
            ).format(num=i)
            for i in range(1, 4)
        }
        options[''] = _('By default - {option}').format(option=options[str(default)])
        return options

    @staticmethod
    def _get_paired_bye_result_options() -> dict[str, str]:
        options: dict[str, str] = {
            '': '',
            WebContext.value_to_form_data(Result.GAIN.value): _('Points for gain (full-point bye)'),
            WebContext.value_to_form_data(Result.DRAW.value): _('Points for draw (half-point bye)'),
            WebContext.value_to_form_data(Result.LOSS.value): _('Points for loss (zero-point bye)'),
        }
        default_option: str = WebContext.value_to_form_data(PapiWebConfig.default_paired_bye_result.value)
        options[''] = _('By default - {option}').format(option=options[default_option])
        return options

    @staticmethod
    def _get_tie_break_options() -> dict[str, str]:
        return {
            WebContext.value_to_form_data(tie_break): tie_break.name
            for tie_break in iter(PapiTieBreak)
        }

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
            options[WebContext.value_to_form_data(timer.id)] = _('Timer {timer_uniq_id}').format(
                timer_uniq_id=timer.uniq_id
            )
        return options

    @staticmethod
    def _get_input_exit_button_options() -> dict[str, str]:
        options: dict[str, str] = {
            '': '-',
            'on': _('Display the exit button'),
            'off': _('Hide the exit button'),
        }
        options[''] = _('By default - {option}').format(
            option=options['on' if PapiWebConfig.default_input_exit_button else 'off']
        )
        return options

    @staticmethod
    def _get_players_show_unpaired_options() -> dict[str, str]:
        options: dict[str, str] = {
            '': '-',
            'off': _('Display only paired players'),
            'on': _('Display all the players, paired and unpaired'),
        }
        options[''] = _('By default - {option}').format(
            option=options[
                'on' if PapiWebConfig.default_players_show_unpaired else 'off'
            ]
        )
        return options

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
            errors['record_illegal_moves'] = _('Invalid value [{value}].').format(
                value=data[field]
            )
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
                    response = requests.get(rules, timeout=REQUEST_TIMEOUT)
                    if response.status_code != 200:
                        errors[field] = _(
                            'URL [{url}] responded code [{code}].'
                        ).format(url=rules, code=response.status_code)
                except requests.ConnectionError as ce:
                    errors[field] = _(
                        'URL [{url}] did not respond (error: [{error}]).'
                    ).format(url=rules, error=str(ce))
            else:
                if rules.find('..') != -1:
                    errors[field] = _('Incorrect path [{path}].').format(path=rules)
                    data[field] = ''
                else:
                    file: Path = Path(rules)
                    if not file.exists() or not file.is_file():
                        errors[field] = _('File [{file}] not found.').format(file=rules)
                    elif file.suffix.lower() != '.pdf':
                        errors[field] = _(
                            'Wrong file extension [{ext}] ([pdf] expected).'
                        ).format(ext=file.suffix)
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
                errors[field] = _(
                    'Invalid color [{color}] ([#RRGGBB] expected).'
                ).format(color={data[field]})
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
                errors['uniq_id'] = _('Character [{char}] is not allowed.').format(
                    char='/'
                )
            else:
                event_uniq_ids: list[str] = EventLoader.get(
                    request=request
                ).event_uniq_ids
                match action:
                    case 'clone' | 'create':
                        if uniq_id in event_uniq_ids:
                            errors['uniq_id'] = _(
                                'Event [{uniq_id}] already exists.'
                            ).format(uniq_id=uniq_id)
                    case 'update':
                        if uniq_id != admin_event.uniq_id and uniq_id in event_uniq_ids:
                            errors['uniq_id'] = _(
                                'Event [{uniq_id}] already exists.'
                            ).format(uniq_id=uniq_id)
                    case _:
                        raise ValueError(f'action=[{action}]')
        name: str | None = None
        federation: str | None = None
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
        message_text: str | None = None
        message_color: str | None = None
        message_background_color: str | None = None
        match action:
            case 'clone' | 'update' | 'create':
                name = WebContext.form_data_to_str(data, field := 'name')
                if not name:
                    errors[field] = _('Please enter the name of the event.')
                federation = WebContext.form_data_to_str(
                    data, field := 'federation', PapiWebConfig().default_federation
                )
                if federation not in PapiWebConfig.federations:
                    # should never happen, not translated.
                    errors[field] = f'Invalid federation value [{data[field]}].'
                    data[field] = ''
                start_str: str | None = WebContext.form_data_to_str(
                    data, field := 'start'
                )
                if not start_str:
                    errors[field] = _('Please enter the start date of the event.')
                else:
                    start = time.mktime(
                        datetime.strptime(start_str, '%Y-%m-%dT%H:%M').timetuple()
                    )
                stop_str: str | None = WebContext.form_data_to_str(
                    data, field := 'stop'
                )
                if not stop_str:
                    errors[field] = _('Please enter the end date of the event.')
                else:
                    stop = time.mktime(
                        datetime.strptime(stop_str, '%Y-%m-%dT%H:%M').timetuple()
                    )
                if 'start' not in errors and 'stop' not in errors and start > stop:
                    errors[field] = _('Please enter a date after the start date.')
                public = WebContext.form_data_to_bool(data, 'public')
                path = WebContext.form_data_to_str(data, 'path')
                update_password = WebContext.form_data_to_str(data, 'update_password')
                field = 'background_image'
                hide_background_image = WebContext.form_data_to_bool(
                    data, field + '_checkbox'
                )
                if not hide_background_image:
                    if background_image := WebContext.form_data_to_str(data, field, ''):
                        if validators.url(background_image):
                            try:
                                response = requests.get(background_image, timeout=REQUEST_TIMEOUT)
                                if response.status_code != 200:
                                    errors[field] = _(
                                        'URL [{url}] responded code [{code}].'
                                    ).format(
                                        url=background_image, code=response.status_code
                                    )
                            except requests.ConnectionError as ce:
                                errors[field] = _(
                                    'URL [{url}] did not respond (error: [{error}]).'
                                ).format(url=background_image, error=str(ce))
                        elif Path(background_image).exists():
                            errors[field] = _(
                                'Please enter a URL or select an image on the right hand side.'
                            )
                        else:
                            background_image = background_image.strip('/')
                            if background_image.find('..') != -1:
                                errors[field] = _('Incorrect path [{path}].').format(
                                    path=background_image
                                )
                                data[field] = ''
                            elif (
                                not (
                                    PapiWebConfig.custom_path / background_image
                                ).exists()
                                and not (
                                    PapiWebConfig.embedded_custom_path
                                    / background_image
                                ).exists()
                            ):
                                errors[field] = _('File [{file}] not found.').format(
                                    file=background_image
                                )
                background_color = cls._admin_validate_background_color_update_data(
                    data, errors
                )
                record_illegal_moves = (
                    cls._admin_validate_record_illegal_moves_update_data(data, errors)
                )
                rules = cls._admin_validate_rules_update_data(data, errors)
                field: str = 'message_text'
                message_text = WebContext.form_data_to_str(data, field)
                field: str = 'message_color'
                if not WebContext.form_data_to_bool(data, field + '_checkbox'):
                    try:
                        message_color = WebContext.form_data_to_rgb(data, field)
                    except ValueError:
                        errors[field] = _(
                            'Invalid color [{color}] ([#RRGGBB] expected).'
                        ).format(color={data[field]})
                field: str = 'message_background_color'
                if not WebContext.form_data_to_bool(data, field + '_checkbox'):
                    try:
                        message_background_color = WebContext.form_data_to_rgb(
                            data, field
                        )
                    except ValueError:
                        errors[field] = _(
                            'Invalid color [{color}] ([#RRGGBB] expected).'
                        ).format(color={data[field]})
                pass
            case 'delete':
                pass
            case _:
                raise ValueError(f'action=[{action}]')
    
        # Have plugins validate their fields and return private plugin data
        per_plugin_tournament_data = plugin_manager.hook.get_validated_event_form_fields(action=action, event=admin_event, data=data, errors=errors)
        plugin_data = {key: value for data in per_plugin_tournament_data for key, value in data.items()}
        
        return StoredEvent(
            uniq_id=uniq_id,
            name=name,
            federation=federation,
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
            message_text=message_text,
            message_color=message_color,
            message_background_color=message_background_color,
            errors=errors,

            # Timer defaults are edited in the timers tab.  We copy the values from the admin_event if it exists.
            timer_colors = admin_event.timer_colors if admin_event else {i: None for i in range(1, 4)},
            timer_delays = admin_event.timer_delays if admin_event else {i: None for i in range(1, 4)},
            
            plugin_data=plugin_data
        )

    @staticmethod
    def background_images_jstree_data(background_image: str) -> list[dict[str, Any]]:
        dirs: list[str] = []
        files: list[str] = []
        for custom_path in [
            PapiWebConfig.embedded_custom_path,
            PapiWebConfig.custom_path,
        ]:
            for item in custom_path.rglob('*'):
                item_str = (
                    str(item)
                    .replace(str(custom_path), '')
                    .replace('\\', '/')
                    .lstrip('/')
                )
                if item.is_dir():
                    if item_str not in dirs:
                        dirs.append(item_str)
                else:
                    if item_str not in files:
                        files.append(item_str)
        dir_nodes: list[dict[str, str]] = [
            {
                'id': d or '#',
                'parent': '/'.join(d.split('/')[:-1]) or '#',
                'text': f' {d.split("/")[-1]}',
                'state': {},
                'icon': 'bi-folder',
            }
            for d in dirs
        ]
        file_nodes: list[dict[str, str]] = [
            {
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
                },
            }
            for f in files
        ]
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
                name = EventLoader.get(request).get_unused_event_name(
                    admin_event.stored_event.name
                )
                uniq_id = EventLoader.get(request).get_unused_event_uniq_id(
                    admin_event.stored_event.uniq_id
                )
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
            case 'delete':
                pass
            case _:
                raise ValueError(f'action=[{action}]')
        public: bool | None = None
        federation: str | None = None
        hide_background_image: bool | None = None
        background_image: str | None = None
        background_color: str | None = None
        path: str | None = None
        update_password: str | None = None
        record_illegal_moves: int | None = None
        rules: str | None = None
        message_text: str | None = None
        message_color: str | None = None
        message_background_color: str | None = None
        match action:
            case 'update' | 'clone':
                public = admin_event.stored_event.public
                federation = admin_event.stored_event.federation
                hide_background_image = admin_event.stored_event.hide_background_image
                background_image = admin_event.stored_event.background_image
                background_color = admin_event.stored_event.background_color
                path = admin_event.stored_event.path
                update_password = admin_event.stored_event.update_password
                record_illegal_moves = admin_event.stored_event.record_illegal_moves
                rules = admin_event.stored_event.rules
                message_text = admin_event.stored_event.message_text
                message_color = admin_event.message_color
                message_background_color = admin_event.message_background_color
            case 'create':
                public = False
                federation = PapiWebConfig().federation.name
                hide_background_image = PapiWebConfig.default_hide_background_image
            case 'delete':
                pass
            case _:
                raise ValueError(f'action=[{action}]')
            
        per_plugin_form_data = plugin_manager.hook.get_event_form_data(event=admin_event)
        plugin_form_data = {key: value for data in per_plugin_form_data for key, value in data.items()}

        return (
            {
                'uniq_id': WebContext.value_to_form_data(uniq_id),
                'name': WebContext.value_to_form_data(name),
                'public': WebContext.value_to_form_data(public),
                'federation': WebContext.value_to_form_data(federation),
                'start': WebContext.value_to_datetime_form_data(start),
                'stop': WebContext.value_to_datetime_form_data(stop),
                'background_image_checkbox': WebContext.value_to_form_data(
                    hide_background_image
                ),
                'background_image': WebContext.value_to_form_data(background_image),
                'background_color': WebContext.value_to_form_data(background_color),
                'background_color_checkbox': WebContext.value_to_form_data(
                    background_color is None
                ),
                'path': WebContext.value_to_form_data(path),
                'update_password': WebContext.value_to_form_data(update_password),
                'record_illegal_moves': WebContext.value_to_form_data(
                    record_illegal_moves
                ),
                'rules': WebContext.value_to_form_data(rules),
                'message_text': WebContext.value_to_form_data(message_text),
                'message_color_checkbox': WebContext.value_to_form_data(
                    message_color is None
                ),
                'message_color': WebContext.value_to_form_data(message_color),
                'message_background_color_checkbox': WebContext.value_to_form_data(
                    message_background_color is None
                ),
                'message_background_color': WebContext.value_to_form_data(
                    message_background_color
                ),
            } | plugin_form_data
        )

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
    def _admin_render(
        cls,
        web_context: AdminWebContext,
        modal: str | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
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
        if not web_context.admin_tab or nav_tabs[web_context.admin_tab]['disabled']:
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
            'messages': Message.messages(web_context.request),
            'nav_tabs': nav_tabs,
            'admin_events_show_details': (
                SessionHandler.get_session_admin_events_show_details(
                    web_context.request
                )
            ),
            'event_card_blocks': event_card_blocks,
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
                        'plugin_form_fields_templates': plugin_form_fields_templates,
                    }
                    stored_config: StoredConfig = cls._admin_validate_config_update_data(data)
                    errors = stored_config.errors
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
                federation_options: dict[str, str] = {
                    PapiWebConfig.default_federation: _('By default - {option}').format(
                        option=f'{papi_web_config.default_federation} - {papi_web_config.federations[papi_web_config.default_federation]}'
                    ),
                } | {
                    federation_id: f'{federation_id} - {federation_name}'
                    for federation_id, federation_name in papi_web_config.federations.items()
                    if federation_id != papi_web_config.default_federation
                }
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
                context |= {
                    'log_level_options': log_level_options,
                    'launch_browser_options': launch_browser_options,
                    'locale_options': locale_options,
                    'federation_options': federation_options,
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
                    'federations': PapiWebConfig.federations,
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
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
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
