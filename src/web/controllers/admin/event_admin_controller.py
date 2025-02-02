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

from common import unicode_normalize, DEVEL_ENV
from common.exception import PapiWebException
from common.i18n import _
from common.logger import get_logger
from common.papi_web_config import PapiWebConfig
from data.event import Event
from data.loader import EventLoader
from data.player import Player, ClubTuple, LeagueTuple, FederationTuple
from data.util import PlayerGender, PlayerFFELicence, PlayerCategory
from database.sqlite.event_database import EventDatabase
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
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_event_tab': self.admin_event_tab,
            'admin_event': self.admin_event,
        }

    def get_tournament_options(self) -> dict[str, str]:
        return {
            str(tournament.id): f'{tournament.name} ({tournament.uniq_id})'
            for tournament in self.admin_event.tournaments_sorted_by_uniq_id
        }


class AbstractEventAdminController(AbstractIndexAdminController):

    @classmethod
    def _get_admin_event_render_context(
            cls,
            web_context: EventAdminWebContext,
    ) -> dict[str, Any]:
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
                'title': admin_event.uniq_id,
                'template': 'event/tab.html',
                'icon_class': 'bi-gear-fill',
            },
            'tournaments': {
                'title': _('Tournaments ({num})').format(num=len(admin_event.tournaments_by_id) or '-'),
                'template': 'tournaments/tab.html',
            },
            'players': {
                'title': _('Players ({num})').format(num=admin_event.players_number or '-'),
                'template': 'players/tab.html',
            },
            'screens': {
                'title': _('Screens ({num})').format(num=len(admin_event.basic_screens_by_id) or '-'),
                'template': 'screens/tab.html',
            },
            'families': {
                'title': _('Families ({num})').format(num=len(admin_event.families_by_id) or '-'),
                'template': 'families/tab.html',
            },
            'rotators': {
                'title': _('Rotators ({num})').format(num=len(admin_event.rotators_by_id) or '-'),
                'template': 'rotators/tab.html',
            },
            'timers': {
                'title': _('Timers ({num})').format(num=len(admin_event.timers_by_id) or '-'),
                'template': 'timers/tab.html',
            },
            'chessevents': {
                'title': _('ChessEvent ({num})').format(num=len(admin_event.chessevents_by_id) or '-'),
                'template': 'chessevents/tab.html',
            },
        }
        if not web_context.admin_event_tab:
            web_context.admin_event_tab = list(nav_tabs.keys())[0]
        template_context: dict[str, Any] = web_context.template_context | {
            'messages': Message.messages(web_context.request),
            'logging_levels': logging_levels,
            'nav_tabs': nav_tabs
        }
        match web_context.admin_event_tab:
            case 'config':
                pass
            case 'tournaments':
                pass
            case 'players':
                # The federations that will be shown on the federation select list
                players_federations: list[FederationTuple] = sorted({
                    player.federation_tuple for player in web_context.admin_event.players_by_id.values()})
                # The federations that will be selected on the federation select list and used to filter the players
                filter_federations: list[FederationTuple] = [
                    f for f in SessionHandler.get_session_admin_players_filter_federations(web_context.request)
                    if f in players_federations
                ]
                # The leagues that will be shown on the league select list
                players_leagues: list[LeagueTuple] = sorted({
                    player.league_tuple for player in web_context.admin_event.players_by_id.values()
                    if not filter_federations or player.federation_tuple in filter_federations
                })
                # The leagues that will be selected on the league select list and used to filter the players
                filter_leagues: list[LeagueTuple] = [
                    l for l in SessionHandler.get_session_admin_players_filter_leagues(web_context.request)
                    if l in players_leagues
                ]
                # The clubs that will be shown on the club select list
                players_clubs: list[ClubTuple] = sorted({
                    player.club_tuple for player in web_context.admin_event.players_by_id.values()
                    if not filter_leagues or player.league_tuple in filter_leagues
                })
                # The clubs that will be selected on the club select list and used to filter the players
                filter_clubs: list[ClubTuple] = [
                    c for c in SessionHandler.get_session_admin_players_filter_clubs(web_context.request)
                    if c in players_clubs
                ]
                # The genders that will be shown on the gender select list
                players_genders: list[PlayerGender] = sorted(
                    {player.gender for player in web_context.admin_event.players_by_id.values()})
                # The genders that will be selected on the gender select list and used to filter the players
                filter_genders: list[PlayerGender] = SessionHandler.get_session_admin_players_filter_genders(
                    web_context.request)
                # The years or birth that will be shown on the year of birth select list
                players_yobs: list[str] = sorted(
                    {player.year_of_birth for player in web_context.admin_event.players_by_id.values()})
                # The licences that will be shown on the licence select list
                players_licences: list[PlayerFFELicence] = sorted(
                    {player.ffe_licence for player in admin_event.players_by_id.values()})
                # The licences that will be selected on the licence select list and used to filter the players
                filter_licences: list[PlayerFFELicence] = SessionHandler.get_session_admin_players_filter_licences(
                    web_context.request)
                # The check-in statuses that will be selected on the check-in status select list and used to filter the players
                players_check_ins: list[bool | None] = [None, True, False]
                # The check-in statuses that will be selected on the check-in status select list and used to filter the players
                filter_check_ins: list[bool | None] = SessionHandler.get_session_admin_players_filter_check_ins(
                    web_context.request)
                # The tournaments that will be selected on the tournament select list and used to filter the players
                filter_tournaments: list[int] = SessionHandler.get_session_admin_players_filter_tournaments(
                    web_context.request)
                # The categories that will be shown on the category select list
                players_categories: list[PlayerCategory] = sorted(
                    {player.category for player in admin_event.players_by_id.values()})
                # The categories that will be selected on the category select list and used to filter the players
                filter_categories: list[PlayerCategory] = SessionHandler.get_session_admin_players_filter_categories(
                    web_context.request)
                # The name the players must match
                filter_name: str = SessionHandler.get_session_admin_players_filter_name(web_context.request)
                filter_name_parts: list[str] = filter_name.split(' ')
                # The origin (federation+league+club) the players must match
                filter_origin: str = SessionHandler.get_session_admin_players_filter_origin(web_context.request)
                filter_origin_parts: list[str] = filter_origin.split(' ')
                match SessionHandler.get_session_admin_players_sort(web_context.request):
                    case 'alpha':
                        sort_key = lambda player: (player.last_name, player.first_name)
                    case 'rating_desc':
                        sort_key = lambda player: (-player.rating, player.last_name, player.first_name)
                    case 'rating_asc':
                        sort_key = lambda player: (player.rating, player.last_name, player.first_name)
                    case 'yob_desc':
                        sort_key = lambda player: (-player.year_of_birth, player.last_name, player.first_name)
                    case 'yob_asc':
                        sort_key = lambda player: (player.year_of_birth, player.last_name, player.first_name)
                    case 'category_desc':
                        sort_key = lambda player: (-player.category, player.last_name, player.first_name)
                    case 'category_asc':
                        sort_key = lambda player: (player.category, player.last_name, player.first_name)
                    case 'origin':
                        sort_key = lambda player: (
                        player.federation, player.league, player.club, player.last_name, player.first_name)
                    case 'tournament':
                        sort_key = lambda player: (
                            web_context.admin_event.tournaments_by_id[player.tournament_id].uniq_id, -player.rating,
                            player.last_name, player.first_name
                        )
                    case _:
                        raise ValueError(f'sort={SessionHandler.get_session_admin_players_sort(web_context.request)}')
                #0 real players only
                #1 all or no genders selected, or player matches
                #2 all or no licences selected, or player matches
                #3 all or no check_ins selected, or player matches
                #4 less than two tournaments, all or no tournaments selected, or player matches
                #5 less than two federations, all or no federations selected, or player matches
                #6 less than two leagues, all or no leagues selected, or player matches
                #7 less than two clubs, all or no clubs selected, or player matches
                players: list[Player] = sorted([
                    player for player in web_context.admin_event.players_by_id.values()
                    if (player.ref_id > 1 and len(filter_genders) in [0, 3] or player.gender.value in filter_genders) \
                       and (len(filter_licences) in [0, len(players_licences)] or player.ffe_licence in filter_licences) \
                       and (len(filter_categories) in [0, len(players_categories)] or player.category in filter_categories) \
                       and (len(filter_check_ins) in [0, 3] or (player.can_check_in_out and player.check_in in filter_check_ins) or (not player.can_check_in_out and None in filter_check_ins)) \
                       and (len(filter_tournaments) in [0, len(web_context.admin_event.tournaments_by_id)] or player.tournament_id in filter_tournaments) \
                       and (len(filter_federations) in [0, len(players_federations)] or player.federation_tuple in filter_federations) \
                       and (len(filter_leagues) in [0, len(players_leagues)] or player.league_tuple in filter_leagues) \
                       and (len(filter_clubs) in [0, len(players_clubs)] or player.club_tuple in filter_clubs) \
                       and all({filter_name_part in unicode_normalize(f'{player.last_name} {player.first_name}'.lower()) for filter_name_part in filter_name_parts}) \
                       and all({filter_origin_part in unicode_normalize(f'{player.federation} {player.league} {player.club}'.lower()) for filter_origin_part in filter_origin_parts})
                    ], key=sort_key)
                template_context |= {
                    'admin_players': players,
                    'admin_players_columns': [
                        'check_in', 'name', 'rating', 'federation', 'league', 'club', 'yob', 'category', 'mail',
                        'phone', 'gender', 'fixed', 'fide', 'ffe', 'owed_paid', 'tournament', 'comment', 'history',
                    ],
                    'admin_players_sort': SessionHandler.get_session_admin_players_sort(web_context.request),
                    'admin_players_federations': players_federations,
                    'admin_players_leagues': players_leagues,
                    'admin_players_clubs': players_clubs,
                    'admin_players_yobs': players_yobs,
                    'admin_players_categories': players_categories,
                    'admin_players_genders': players_genders,
                    'admin_players_licences': players_licences,
                    'admin_players_check_ins': players_check_ins,
                    'admin_players_filter_columns': SessionHandler.get_session_admin_players_filter_columns(
                        web_context.request),
                    'admin_players_filter_federations': SessionHandler.get_session_admin_players_filter_federations(
                        web_context.request),
                    'admin_players_filter_leagues': SessionHandler.get_session_admin_players_filter_leagues(
                        web_context.request),
                    'admin_players_filter_clubs': SessionHandler.get_session_admin_players_filter_clubs(
                        web_context.request),
                    'admin_players_filter_genders': SessionHandler.get_session_admin_players_filter_genders(
                        web_context.request),
                    'admin_players_filter_licences': SessionHandler.get_session_admin_players_filter_licences(
                        web_context.request),
                    'admin_players_filter_check_ins': SessionHandler.get_session_admin_players_filter_check_ins(
                        web_context.request),
                    'admin_players_filter_tournaments': SessionHandler.get_session_admin_players_filter_tournaments(
                        web_context.request),
                    'admin_players_filter_categories': SessionHandler.get_session_admin_players_filter_categories(
                        web_context.request),
                    'admin_players_filter_name': SessionHandler.get_session_admin_players_filter_name(
                        web_context.request),
                    'admin_players_filter_origin': SessionHandler.get_session_admin_players_filter_origin(
                        web_context.request),
                }
            case 'screens':
                template_context |= {
                    'admin_screens_show_family_screens': SessionHandler.get_session_admin_screens_show_family_screens(
                        web_context.request),
                    'admin_screens_show_details': SessionHandler.get_session_admin_screens_show_details(
                        web_context.request),
                    'admin_screens_screen_types': SessionHandler.get_session_admin_screens_screen_types(
                        web_context.request),
                }
            case 'families':
                template_context |= {
                    'admin_families_show_details': SessionHandler.get_session_admin_families_show_details(
                        web_context.request),
                }
            case 'rotators':
                template_context |= {
                    'admin_rotators_show_details': SessionHandler.get_session_admin_rotators_show_details(
                        web_context.request),
                }
            case 'timers':
                pass
            case 'chessevents':
                pass
            case _:
                raise ValueError(f'admin_event_tab={web_context.admin_event_tab}')
        return template_context

    @classmethod
    def _admin_event_render(
            cls,
            template_context: dict[str, Any],
    ) -> Template:
        return HTMXTemplate(
            template_name="admin/event.html",
            context=template_context)


class EventAdminController(AbstractEventAdminController):

    @classmethod
    def _admin_event_tab_render(
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
            locale: str | None = None,
            modal: str | None = None,
            action: str | None = None,
            data: dict[str, str] | None = None,
            errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        self.set_locale(request, locale)
        return self._admin_event_tab_render(
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
            locale: str | None,
    ) -> Template | ClientRedirect:
        return self._admin_event(
            request,
            event_uniq_id=event_uniq_id,
            admin_event_tab=None,
            locale=locale,
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
            locale: str | None,
            admin_screens_show_family_screens: bool | None,
            admin_screens_show_details: bool | None,
            admin_families_show_details: bool | None,
            admin_rotators_show_details: bool | None,
            admin_screens_show_boards: bool | None,
            admin_screens_show_input: bool | None,
            admin_screens_show_players: bool | None,
            admin_screens_show_results: bool | None,
            admin_screens_show_image: bool | None,
            admin_players_sort: str | None = None,
            admin_players_filter_columns: list[str] | None = None,
            admin_players_filter_federations: list[str] | None = None,
            admin_players_filter_leagues: list[str] | None = None,
            admin_players_filter_clubs: list[str] | None = None,
            admin_players_filter_genders: list[int] | None = None,
            admin_players_filter_licences: list[int] | None = None,
            admin_players_filter_check_ins: list[int] | None = None,
            admin_players_filter_tournaments: list[int] | None = None,
            admin_players_filter_categories: list[int] | None = None,
            admin_players_filter_name: str | None = None,
            admin_players_filter_origin: str | None = None,
            admin_players_clear_filters: int | None = None,
    ) -> Template | ClientRedirect:
        match admin_event_tab:
            case 'config':
                pass
            case 'tournaments':
                pass
            case 'players':
                if admin_players_sort is not None:
                    SessionHandler.set_session_admin_players_sort(request, admin_players_sort)
                elif admin_players_filter_columns is not None:
                    SessionHandler.set_session_admin_players_filter_columns(request, [
                        column for column in admin_players_filter_columns if column  # '' must be ignored
                    ])
                elif admin_players_filter_federations is not None:
                    SessionHandler.set_session_admin_players_filter_federations(request, [
                        FederationTuple.from_query_param(query_param) for query_param in
                        admin_players_filter_federations
                        if query_param  # '' must be ignored
                    ])
                elif admin_players_filter_leagues is not None:
                    SessionHandler.set_session_admin_players_filter_leagues(request, [
                        LeagueTuple.from_query_param(query_param) for query_param in admin_players_filter_leagues
                        if query_param  # '' must be ignored
                    ])
                elif admin_players_filter_clubs is not None:
                    SessionHandler.set_session_admin_players_filter_clubs(request, [
                        ClubTuple.from_query_param(query_param) for query_param in admin_players_filter_clubs
                        if query_param  # '' must be ignored
                    ])
                elif admin_players_filter_genders is not None:
                    SessionHandler.set_session_admin_players_filter_genders(request, [
                        PlayerGender(query_param) for query_param in admin_players_filter_genders
                        if query_param >= 0  # -1 must be ignored
                    ])
                elif admin_players_filter_licences is not None:
                    SessionHandler.set_session_admin_players_filter_licences(request, [
                        PlayerFFELicence(query_param) for query_param in admin_players_filter_licences
                        if query_param >= 0  # -1 must be ignored
                    ])
                elif admin_players_filter_check_ins is not None:
                    SessionHandler.set_session_admin_players_filter_check_ins(request, [
                        {0: None, 1: False, 2:True, }.get(query_param, None) for query_param in admin_players_filter_check_ins
                        if query_param >= 0  # -1 must be ignored
                    ])
                elif admin_players_filter_tournaments is not None:
                    SessionHandler.set_session_admin_players_filter_tournaments(request, [
                        query_param for query_param in admin_players_filter_tournaments
                        if query_param > 0  # 0 must be ignored
                    ])
                elif admin_players_filter_categories is not None:
                    SessionHandler.set_session_admin_players_filter_categories(request, [
                        PlayerCategory(query_param) for query_param in admin_players_filter_categories
                        if query_param >= 0  # -1 must be ignored
                    ])
                elif admin_players_filter_name is not None:
                    SessionHandler.set_session_admin_players_filter_name(
                        request, unicode_normalize(admin_players_filter_name).lower())
                elif admin_players_filter_origin is not None:
                    SessionHandler.set_session_admin_players_filter_origin(
                        request, unicode_normalize(admin_players_filter_origin).lower())
                elif admin_players_clear_filters:
                    SessionHandler.set_session_admin_players_filter_federations(request, [])
                    SessionHandler.set_session_admin_players_filter_leagues(request, [])
                    SessionHandler.set_session_admin_players_filter_clubs(request, [])
                    SessionHandler.set_session_admin_players_filter_genders(request, [])
                    SessionHandler.set_session_admin_players_filter_licences(request, [])
                    SessionHandler.set_session_admin_players_filter_check_ins(request, [])
                    SessionHandler.set_session_admin_players_filter_tournaments(request, [])
                    SessionHandler.set_session_admin_players_filter_categories(request, [])
                    SessionHandler.set_session_admin_players_filter_name(request, '')
                    SessionHandler.set_session_admin_players_filter_origin(request, '')
            case 'screens':
                if admin_screens_show_family_screens is not None:
                    SessionHandler.set_session_admin_screens_show_family_screens(
                        request, admin_screens_show_family_screens)
                if admin_screens_show_details is not None:
                    SessionHandler.set_session_admin_screens_show_details(request, admin_screens_show_details)
                screen_types: list[str] = SessionHandler.get_session_admin_screens_screen_types(request)
                for screen_type, param in {
                    'boards': admin_screens_show_boards,
                    'input': admin_screens_show_input,
                    'players': admin_screens_show_players,
                    'results': admin_screens_show_results,
                    'image': admin_screens_show_image,
                }.items():
                    if param is not None:
                        if param:
                            screen_types.append(screen_type)
                        else:
                            screen_types.remove(screen_type)
                        SessionHandler.set_session_admin_screens_screen_types(request, screen_types)
                        continue
            case 'families':
                if admin_families_show_details is not None:
                    SessionHandler.set_session_admin_families_show_details(request, admin_families_show_details)
            case 'rotators':
                if admin_rotators_show_details is not None:
                    SessionHandler.set_session_admin_rotators_show_details(request, admin_rotators_show_details)
            case 'chessevents':
                pass
            case 'timers':
                pass
            case _:
                raise ValueError(f'admin_event_tab={admin_event_tab}')
        return self._admin_event(
            request,
            event_uniq_id=event_uniq_id,
            admin_event_tab=admin_event_tab,
            locale=locale,
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
            return self._admin_event_tab_render(
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
                        _('Event [{old_uniq_id}] has been renamed ([{new_uniq_id}]) and updated.').format(
                            olq_uniq_id=web_context.admin_event.uniq_id, new_uniq_id=uniq_id))
                else:
                    Message.success(request, _('Event [{uniq_id}] has been updated.').format(uniq_id=uniq_id))
                event_loader.clear_cache(uniq_id)
                return self._admin_event_tab_render(request, event_uniq_id=uniq_id)
            case 'clone':
                EventDatabase(web_context.admin_event.uniq_id).clone(new_uniq_id=uniq_id)
                with EventDatabase(uniq_id, write=True) as event_database:
                    event_database.update_stored_event(stored_event)
                    event_database.commit()
                Message.success(request, _('Event [{uniq_id}] has been created.').format(uniq_id=uniq_id))
                event_loader.clear_cache(uniq_id)
                return self._admin_event_tab_render(request, event_uniq_id=uniq_id)
            case 'delete':
                try:
                    arch = EventDatabase(web_context.admin_event.uniq_id).delete()
                except PermissionError as ex:
                    return AbstractController.redirect_error(request, f'Archiving the database failed: {ex}')
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
