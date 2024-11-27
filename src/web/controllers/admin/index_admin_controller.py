import time
from datetime import datetime
from logging import Logger
from typing import Annotated, Any

from litestar import get, post
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import HTMXTemplate, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, Redirect

from common import format_timestamp_date
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
    def background_image(self) -> str:
        if self.admin_tab in ['archives', 'config', ]:
            return PapiWebConfig.default_background_image
        else:
            return ''

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
            '0': 'Aucun enregistrement des coups illégaux',
            '1': 'Maximum 1 coup illégal',
            '2': 'Maximum 2 coups illégaux',
            '3': 'Maximum 3 coups illégaux',
        }
        options[''] = f'Par défaut ({options[str(default)]})'
        return options

    @staticmethod
    def _get_timer_color_texts(delays: dict[int, int]) -> dict[int, str]:
        return {
            1: f'La couleur n°1 est utilisée jusqu\'à {delays[1]} minutes avant le début des rondes (délai n°1), '
               f'la couleur change ensuite progressivement jusqu\'à la couleur n°2 ({delays[2]} minutes avant le '
               f'début des rondes).',
            2: f'La couleur n°2 est utilisée {delays[2]} minutes avant le début des rondes (délai n°2), la couleur '
               f'change ensuite progressivement jusqu\'à la couleur n°3 (au début des rondes).',
            3: f'La couleur n°3 est utilisée à partir du début des rondes et pendant {delays[3]} minutes (délai n°3).',
        }

    @staticmethod
    def _get_screen_type_options(family_screens_only: bool) -> dict[str, str]:
        options: dict[str, str] = {
            '': '-',
            'boards': 'Appariements par échiquier',
            'input': 'Saisie des résultats',
            'players': 'Appariements par ordre alphabétique',
        }
        if not family_screens_only:
            options['results'] = 'Derniers résultats'
            options['image'] = 'Image'
        return options

    @staticmethod
    def _get_timer_options(event: Event) -> dict[str, str]:
        options: dict[str, str] = {
            '': 'Pas de chronomètre' if event.timers_by_id else 'Aucun chronomètre enregistré',
        }
        for timer in event.timers_by_id.values():
            options[str(timer.id)] = f'Chronomètre [{timer.uniq_id}]'
        return options

    @staticmethod
    def _get_input_exit_button_options() -> dict[str, str]:
        options: dict[str, str] = {
            '': '-',
            'on': 'Le bouton de sortie d\'écran est affiché',
            'off': 'Le bouton de sortie d\'écran n\'est pas affiché',
        }
        options[''] = f'Par défaut ({options["on" if PapiWebConfig.default_input_exit_button else "off"]})'
        return options

    @staticmethod
    def _get_players_show_unpaired_options() -> dict[str, str]:
        options: dict[str, str] = {
            '': '-',
            'off': 'Affichage seulement des joueur·euses apparié·es',
            'on': 'Affichage de tou·tes les joueur·euses, apparié·es ou non',
        }
        options[''] = f'Par défaut ({options["on" if PapiWebConfig.default_players_show_unpaired else "off"]})'
        return options


class AbstractIndexAdminController(AbstractAdminController):

    @staticmethod
    def _admin_validate_event_create_data(
            request: HTMXRequest,
            data: dict[str, str] | None = None,
    ) -> StoredEvent:
        if data is None:
            data = {}
        errors: dict[str, str] = {}
        uniq_id: str | None = WebContext.form_data_to_str(data, 'uniq_id')
        if not uniq_id:
            errors['uniq_id'] = 'Veuillez entrer l\'identifiant de l\'évènement.'
        elif uniq_id.find('/') != -1:
            errors['uniq_id'] = "le caractère « / » n\'est pas autorisé"
        else:
            event_uniq_ids: list[str] = EventLoader.get(request=request).event_uniq_ids
            if uniq_id in event_uniq_ids:
                errors['uniq_id'] = f'L\'évènement [{uniq_id}] existe déjà.'
        name: str | None = WebContext.form_data_to_str(data, 'name')
        start: float | None = None
        stop: float | None = None
        if not name:
            errors['name'] = 'Veuillez entrer le nom de l\'évènement.'
        start_str: str | None = WebContext.form_data_to_str(data, 'start')
        if not start_str:
            errors['start'] = 'Veuillez entrer la date de début de l\'évènement.'
        else:
            start = time.mktime(datetime.strptime(start_str, '%Y-%m-%dT%H:%M').timetuple())
        stop_str: str | None = WebContext.form_data_to_str(data, 'stop')
        if not stop_str:
            errors['stop'] = 'Veuillez entrer la date de fin de l\'évènement.'
        else:
            stop = time.mktime(datetime.strptime(stop_str, '%Y-%m-%dT%H:%M').timetuple())
        if 'start' not in errors and 'stop' not in errors and start > stop:
            errors['stop'] = 'Veuillez entrer la date postérieure à la date de début.'
        public: bool | None = WebContext.form_data_to_bool(data, 'public')
        return StoredEvent(
            uniq_id=uniq_id,
            name=name,
            start=start,
            stop=stop,
            public=public,
            path=None,
            background_image=None,
            background_color=None,
            update_password=None,
            record_illegal_moves=None,
            timer_colors={i: None for i in range(1, 4)},
            timer_delays={i: None for i in range(1, 4)},
            errors=errors,
        )

    @classmethod
    def _admin_render(
            cls,
            request: HTMXRequest,
            admin_tab: str | None = None,
            modal: str | None = None,
            data: dict[str, str] | None = None,
            errors:  dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: AdminWebContext = AdminWebContext(request, data=None, admin_tab=admin_tab)
        if web_context.error:
            return web_context.error
        event_loader: EventLoader = EventLoader.get(request=request)
        archive_loader: ArchiveLoader = ArchiveLoader.get(request=request)
        nav_tabs: dict[str, dict[str, Any]] = {
            'current_events': {
                'title': f'Évènements en cours ({len(event_loader.current_events) or "-"})',
                'template': 'admin_events.html',
                'events': event_loader.current_events,
                'disabled': not event_loader.current_events,
                'empty_str': 'Aucun évènement en cours.',
                'icon_class': 'bi-calendar',
            },
            'coming_events': {
                'title': f'Évènements à venir ({len(event_loader.coming_events) or "-"})',
                'template': 'admin_events.html',
                'events': event_loader.coming_events,
                'disabled': not event_loader.coming_events,
                'empty_str': 'Aucun évènement à venir.',
                'icon_class': 'bi-calendar-check',
            },
            'passed_events': {
                'title': f'Évènements passés ({len(event_loader.passed_events) or "-"})',
                'template': 'admin_events.html',
                'events': event_loader.passed_events,
                'disabled': not event_loader.passed_events,
                'empty_str': 'Aucun évènement passé.',
                'icon_class': 'bi-calendar-minus',
            },
            'archives': {
                'title': f'Archives ({len(archive_loader.archives_sorted_by_date) or "-"})',
                'template': 'admin_archives.html',
                'archives': archive_loader.archives_sorted_by_date,
                'disabled': not archive_loader.archives_sorted_by_date,
                'empty_str': 'Aucun évènement archivé.',
                'icon_class': 'bi-archive-fill',
            },
            'config': {
                'title': 'Configuration Papi-web',
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
            'messages': Message.messages(request),
            'nav_tabs': nav_tabs,
            'admin_columns': SessionHandler.get_session_admin_columns(request),
        }
        match modal:
            case None:
                pass
            case 'event':
                if data is None:
                    today_str: str = format_timestamp_date()
                    start = time.mktime(datetime.strptime(
                        f'{today_str} 00:00', '%Y-%m-%d %H:%M').timetuple())
                    stop = time.mktime(datetime.strptime(
                        f'{today_str} 23:59', '%Y-%m-%d %H:%M').timetuple())
                    data: dict[str, str] = {
                        'uniq_id': '',
                        'public': WebContext.value_to_form_data(False),
                        'start': WebContext.value_to_datetime_form_data(start),
                        'stop': WebContext.value_to_datetime_form_data(stop),
                    }
                    stored_event: StoredEvent = cls._admin_validate_event_create_data(request, data)
                    errors = stored_event.errors
                if errors is None:
                    errors = {}
                context |= {
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
            modal: str | None = None,
            data: dict[str, str] | None = None,
            errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        if admin_columns is not None:
            SessionHandler.set_session_admin_columns(request, admin_columns)
        return cls._admin_render(request, admin_tab=admin_tab, modal=modal, data=data, errors=errors)

    @get(
        path='/admin',
        name='admin',
        cache=1,
    )
    async def htmx_admin(
            self, request: HTMXRequest,
            admin_columns: int | None,
    ) -> Template | ClientRedirect:
        return self._admin(
            request,
            admin_tab=None,
            admin_columns=admin_columns,
        )

    @get(
        path='/admin/{admin_tab:str}',
        name='admin-tab',
        cache=1,
    )
    async def htmx_admin_tab(
            self, request: HTMXRequest,
            admin_tab: str,
            admin_columns: int | None,
    ) -> Template | ClientRedirect:
        return self._admin(
            request,
            admin_tab=admin_tab,
            admin_columns=admin_columns,
        )

    @get(
        path='/admin/{admin_tab:str}/event-modal/create',
        name='admin-tab-event-create-modal',
        cache=1,
    )
    async def htmx_admin_tab_event_create_modal(
            self, request: HTMXRequest,
            admin_tab: str,
    ) -> Template | ClientRedirect:
        return self._admin(
            request,
            admin_tab=admin_tab,
            modal='event',
        )

    def _admin_event_create(
            self, request: HTMXRequest,
            admin_tab: str,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
    ) -> Template | ClientRedirect | Redirect:
        web_context: AdminWebContext = AdminWebContext(request, data=data, admin_tab=admin_tab)
        if web_context.error:
            return web_context.error
        stored_event: StoredEvent = self._admin_validate_event_create_data(request, data)
        if stored_event.errors:
            return self._admin(
                request, admin_tab=admin_tab, modal='event', data=data, errors=stored_event.errors)
        uniq_id: str = stored_event.uniq_id
        EventDatabase(uniq_id).create()
        with EventDatabase(uniq_id, write=True) as event_database:
            event_database.update_stored_event(stored_event)
            event_database.commit()
        Message.success(request, f'L\'évènement [{uniq_id}] a été créé.')
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
        return self._admin_event_create(
            request,
            admin_tab=admin_tab,
            data=data,
        )
