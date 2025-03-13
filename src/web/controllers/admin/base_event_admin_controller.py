import itertools
import logging
from logging import Logger
from typing import Annotated, Any

from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import HTMXTemplate
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template

from common import unicode_normalize
from common.exception import PapiWebException
from common.i18n import _
from common.logger import get_logger
from data.event import Event
from data.loader import EventLoader
from data.player import Player, Club, Federation
from data.tournament_export import AbstractTournamentExporter, Trf16TournamentExporter, TrfBxTournamentExporter
from data.util import PlayerGender, PlayerCategory, PrintSplit, PrintDocument
from plugins.manager import plugin_manager
from web.controllers.admin.base_admin_controller import (
    AdminWebContext,
    BaseAdminController,
)
from web.messages import Message
from web.session import SessionHandler

logger: Logger = get_logger()


class BaseEventAdminWebContext(AdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str | None,
        admin_event_tab: str | None,
        data: Annotated[
            dict[str, str] | None,
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ):
        super().__init__(request, data=data, admin_tab=None)
        self.admin_event: Event | None = None
        self.admin_event_tab: str | None = admin_event_tab
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
        per_plugin_context = plugin_manager.hook.get_base_event_admin_context(web_context=self)
        plugin_context =  {key: value for context in per_plugin_context for key, value in context.items()}

        return super().template_context | {
            'admin_event_tab': self.admin_event_tab,
            'admin_event': self.admin_event,
        } | plugin_context

    def get_tournament_options(self) -> dict[str, str]:
        return {
            self.value_to_form_data(tournament.id): f'{tournament.name} ({tournament.uniq_id})'
            for tournament in self.admin_event.tournaments_sorted_by_uniq_id
        }

    def get_print_split_options(self) -> dict[str, str]:
        per_plugin_split_options = plugin_manager.hook.get_print_split_options()
        plugin_split_options = [option for options in per_plugin_split_options for option in options]

        return {
            self.value_to_form_data(split): PrintSplit(split).name
            for split in PrintSplit
        } | {
            self.value_to_form_data(plugin_option.url_name): plugin_option.name
            for plugin_option in plugin_split_options
        }

    def get_print_document_options(self) -> dict[str, str]:
        return {
            self.value_to_form_data(document): PrintDocument(document).name
            for document in PrintDocument
        }


class BaseEventAdminController(BaseAdminController):
    @classmethod
    def _get_admin_event_render_context(
        cls,
        web_context: BaseEventAdminWebContext,
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
                'icon_class': 'bi-bug',
            },
            logging.CRITICAL: {
                'name': 'CRITICAL',
                'class': 'bg-danger text-white',
                'icon_class': 'bi-sign-stop',
            },
        }
        nav_tabs: dict[str, dict[str, str]] = {
            'config': {
                'title': admin_event.uniq_id,
                'template': 'event/tab.html',
                'icon_class': 'bi-gear',
            },
            'tournaments': {
                'title': _('Tournaments ({num})').format(
                    num=len(admin_event.tournaments_by_id) or '-'
                ),
                'template': 'tournaments/tab.html',
            },
            'players': {
                'title': _('Players ({num})').format(
                    num=admin_event.player_count or '-'
                ),
                'template': 'players/tab.html',
            },
            'screens': {
                'title': _('Screens ({num})').format(
                    num=len(admin_event.basic_screens_by_id) or '-'
                ),
                'template': 'screens/tab.html',
            },
            'families': {
                'title': _('Families ({num})').format(
                    num=len(admin_event.families_by_id) or '-'
                ),
                'template': 'families/tab.html',
            },
            'rotators': {
                'title': _('Rotators ({num})').format(
                    num=len(admin_event.rotators_by_id) or '-'
                ),
                'template': 'rotators/tab.html',
            },
            'timers': {
                'title': _('Timers ({num})').format(
                    num=len(admin_event.timers_by_id) or '-'
                ),
                'template': 'timers/tab.html',
            },
        }

        if not web_context.admin_event_tab:
            if web_context.admin_event.player_count:
                web_context.admin_event_tab = 'players'
            elif web_context.admin_event.tournaments_by_uniq_id:
                web_context.admin_event_tab = 'tournaments'
            else:
                web_context.admin_event_tab = 'config'

        template_context: dict[str, Any] = web_context.template_context | {
            'messages': Message.messages(web_context.request),
            'logging_levels': logging_levels,
            'nav_tabs': nav_tabs,
        }

        match web_context.admin_event_tab:
            case 'config':
                pass
            case 'tournaments':
                tournament_card_blocks = plugin_manager.hook.get_tournament_card_block_template()
                tournament_exporters: list[AbstractTournamentExporter] = [
                    Trf16TournamentExporter(),
                    TrfBxTournamentExporter()
                ] + list(itertools.chain.from_iterable(
                    plugin_manager.hook.get_extra_tournament_exporters()
                ))
                template_context |= {
                    'paired_bye_result_options': cls._get_paired_bye_result_options(),
                    'tournament_card_blocks': tournament_card_blocks,
                    'tournament_exporters': tournament_exporters,
                    'admin_tournaments_show_details': (
                        SessionHandler.get_session_admin_tournaments_show_details(
                            web_context.request
                        )
                    ),
                }
            case 'players':
                # Allow plugin to provide extra columns
                per_plugin_columns = plugin_manager.hook.get_extra_player_columns()
                extra_columns = {}
                for plugin_columns in per_plugin_columns:
                    for extra_column in plugin_columns:
                        c = extra_columns.setdefault(extra_column.at, [])
                        c.append(extra_column)

                # The federations that will be shown on the federation select list
                players_federations: list[Federation] = sorted(
                    {
                        player.federation
                        for player in web_context.admin_event.players_by_id.values()
                    }
                )
                # The federations that will be selected on the federation select list and used to filter the players
                filter_federations: list[Federation] = [
                    f
                    for f in SessionHandler.get_session_admin_players_filter_federations(
                        web_context.request
                    )
                    if f in players_federations
                ]
                # The clubs that will be shown on the club select list
                players_clubs: list[Club] = sorted(
                    {
                        player.club
                        for player in web_context.admin_event.players_by_id.values()
                    }
                )
                # The clubs that will be selected on the club select list and used to filter the players
                filter_clubs: list[Club] = [
                    c
                    for c in SessionHandler.get_session_admin_players_filter_clubs(
                        web_context.request
                    )
                    if c in players_clubs
                ]
                # The genders that will be shown on the gender select list
                players_genders: list[PlayerGender] = sorted(
                    {
                        player.gender
                        for player in web_context.admin_event.players_by_id.values()
                    }
                )
                # The genders that will be selected on the gender select list and used to filter the players
                filter_genders: list[PlayerGender] = (
                    SessionHandler.get_session_admin_players_filter_genders(
                        web_context.request
                    )
                )
                # The years or birth that will be shown on the year of birth select list
                players_yobs: list[int] = sorted(
                    {
                        player.year_of_birth
                        for player in web_context.admin_event.players_by_id.values()
                    }
                )
                # The check-in statuses that will be selected on the
                # check-in status select list and used to filter the players
                players_check_ins: list[bool | None] = [None, True, False]
                # The check-in statuses that will be selected on the
                # check-in status select list and used to filter the players
                filter_check_ins: list[bool | None] = (
                    SessionHandler.get_session_admin_players_filter_check_ins(
                        web_context.request
                    )
                )
                # The tournaments that will be selected on the tournament select list and used to filter the players
                filter_tournaments: list[int] = (
                    SessionHandler.get_session_admin_players_filter_tournaments(
                        web_context.request
                    )
                )
                # The categories that will be shown on the category select list
                players_categories: list[PlayerCategory] = sorted(
                    {player.category for player in admin_event.players_by_id.values()}
                )
                # The categories that will be selected on the category select list and used to filter the players
                filter_categories: list[PlayerCategory] = (
                    SessionHandler.get_session_admin_players_filter_categories(
                        web_context.request
                    )
                )
                # The name the players must match
                filter_name: str = SessionHandler.get_session_admin_players_filter_name(
                    web_context.request
                )
                filter_name_parts: list[str] = filter_name.split(' ')
                # The origin (federation+league+club) the players must match
                filter_origin: str = (
                    SessionHandler.get_session_admin_players_filter_clubs_search(
                        web_context.request
                    )
                )
                filter_origin_parts: list[str] = filter_origin.split(' ')
                match SessionHandler.get_session_admin_players_sort(
                    web_context.request
                ):
                    case 'alpha':
                        def sort_key(player: Player):
                            return player.last_name, player.first_name

                    case 'rating_desc':
                        def sort_key(player: Player): # pylint: disable=function-redefined
                            return -player.rating, player.last_name, player.first_name

                    case 'rating_asc':
                        def sort_key(player: Player): # pylint: disable=function-redefined
                            return player.rating, player.last_name, player.first_name

                    case 'yob_desc':
                        def sort_key(player: Player): # pylint: disable=function-redefined
                            return (
                                -player.year_of_birth,
                                player.last_name,
                                player.first_name,
                            )

                    case 'yob_asc':
                        def sort_key(player: Player): # pylint: disable=function-redefined
                            return (
                                player.year_of_birth,
                                player.last_name,
                                player.first_name,
                            )

                    case 'category_desc':
                        def sort_key(player: Player): # pylint: disable=function-redefined
                            return -player.category, player.last_name, player.first_name

                    case 'category_asc':
                        def sort_key(player: Player): # pylint: disable=function-redefined
                            return player.category, player.last_name, player.first_name

                    case 'club':
                        def sort_key(player: Player): # pylint: disable=function-redefined
                            return plugin_manager.hook.player_club_sort_key(player=player) or (
                                player.club,
                                player.last_name,
                                player.first_name,
                            )

                    case 'tournament':
                        def sort_key(player: Player): # pylint: disable=function-redefined
                            return (
                                web_context.admin_event.tournaments_by_id[
                                    player.tournament_id
                                ].uniq_id,
                                -player.rating,
                                player.last_name,
                                player.first_name,
                            )

                    case _:
                        raise ValueError(
                            f'sort={SessionHandler.get_session_admin_players_sort(web_context.request)}'
                        )
                # 0 real players only
                # 1 all or no genders selected, or player matches
                # 2 all or no licences selected, or player matches
                # 3 all or no check_ins selected, or player matches
                # 4 less than two tournaments, all or no tournaments selected, or player matches
                # 5 less than two federations, all or no federations selected, or player matches
                # 6 less than two clubs, all or no clubs selected, or player matches

                players: dict[int, Player] = {
                    p.id: p
                    for p in sorted(
                        [
                            player
                            for player in web_context.admin_event.players_by_id.values()
                            if (
                                player.ref_id > 1
                                and len(filter_genders) in [0, 3]
                                or player.gender.value in filter_genders
                            )
                            and (
                                len(filter_categories) in [0, len(players_categories)]
                                or player.category in filter_categories
                            )
                            and (
                                len(filter_check_ins) in [0, 3]
                                or (
                                    player.can_check_in_out
                                    and player.check_in in filter_check_ins
                                )
                                or (
                                    not player.can_check_in_out and None in filter_check_ins
                                )
                            )
                            and (
                                len(filter_tournaments)
                                in [0, len(web_context.admin_event.tournaments_by_id)]
                                or player.tournament_id in filter_tournaments
                            )
                            and (
                                len(filter_federations) in [0, len(players_federations)]
                                or player.federation in filter_federations
                            )
                            and (
                                len(filter_clubs) in [0, len(players_clubs)]
                                or player.club in filter_clubs
                            )
                            and all(
                                {
                                    filter_name_part
                                    in unicode_normalize(
                                        f'{player.last_name} {player.first_name}'.lower()
                                    )
                                    for filter_name_part in filter_name_parts
                                }
                            )
                            and all(
                                {
                                    filter_origin_part
                                    in unicode_normalize(
                                        f'{player.federation} {player.club}'.lower()
                                    )
                                    for filter_origin_part in filter_origin_parts
                                }
                            )
                            and all(plugin_manager.hook.filter_player(web_context=web_context, player=player))
                        ],
                        key=sort_key,
                    )
                }
                template_context |= {
                    'admin_players': players,
                    'admin_players_columns': [
                        'name',
                        'check_in',
                        'rating',
                        'federation',
                        'club',
                        'yob',
                        'category',
                        'mail',
                        'phone',
                        'gender',
                        'fixed',
                        'fide',
                        'owed_paid',
                        'tournament',
                        'comment',
                        'record',
                    ],
                    'admin_players_sort': SessionHandler.get_session_admin_players_sort(
                        web_context.request
                    ),
                    'admin_players_federations': players_federations,
                    'admin_players_clubs': players_clubs,
                    'admin_players_yobs': players_yobs,
                    'admin_players_categories': players_categories,
                    'admin_players_genders': players_genders,
                    'admin_players_check_ins': players_check_ins,
                    'admin_players_filter_columns': SessionHandler.get_session_admin_players_filter_columns(
                        web_context.request
                    ),
                    'admin_players_filter_federations': SessionHandler.get_session_admin_players_filter_federations(
                        web_context.request
                    ),
                    'admin_players_filter_clubs': SessionHandler.get_session_admin_players_filter_clubs(
                        web_context.request
                    ),
                    'admin_players_filter_clubs_search': SessionHandler.get_session_admin_players_filter_clubs_search(
                        web_context.request
                    ),
                    'admin_players_filter_genders': SessionHandler.get_session_admin_players_filter_genders(
                        web_context.request
                    ),
                    'admin_players_filter_check_ins': SessionHandler.get_session_admin_players_filter_check_ins(
                        web_context.request
                    ),
                    'admin_players_filter_tournaments': SessionHandler.get_session_admin_players_filter_tournaments(
                        web_context.request
                    ),
                    'admin_players_filter_categories': SessionHandler.get_session_admin_players_filter_categories(
                        web_context.request
                    ),
                    'admin_players_filter_name': SessionHandler.get_session_admin_players_filter_name(
                        web_context.request
                    ),
                    'admin_players_extra_columns': extra_columns,
                }
            case 'screens':
                template_context |= {
                    'admin_screens_show_family_screens': SessionHandler.get_session_admin_screens_show_family_screens(
                        web_context.request
                    ),
                    'admin_screens_show_details': SessionHandler.get_session_admin_screens_show_details(
                        web_context.request
                    ),
                    'admin_screens_screen_types': SessionHandler.get_session_admin_screens_screen_types(
                        web_context.request
                    ),
                }
            case 'families':
                template_context |= {
                    'admin_families_show_details': SessionHandler.get_session_admin_families_show_details(
                        web_context.request
                    ),
                }
            case 'rotators':
                template_context |= {
                    'admin_rotators_show_details': SessionHandler.get_session_admin_rotators_show_details(
                        web_context.request
                    ),
                }
            case 'timers':
                pass
            case _:
                raise ValueError(f'admin_event_tab={web_context.admin_event_tab}')
        return template_context

    @classmethod
    def _admin_event_render(
        cls,
        template_context: dict[str, Any],
    ) -> Template:
        if "modal" in template_context:
            return HTMXTemplate(
                template_name='admin/modals.html',
                context=template_context,
                re_target='#modal-wrapper',
                trigger_event="modal_opened",
                after="settle"
            )
        return HTMXTemplate(template_name='admin/event_layout.html', context=template_context)

