from collections import defaultdict
from collections.abc import Callable
from datetime import date
from functools import cached_property
from logging import Logger
import math
from typing import Annotated, Any, Iterable

from litestar.exceptions import NotFoundException, ClientException

from common.i18n.utils import normalized_key

from litestar import get, patch, delete, post, Response
from litestar.plugins.htmx import HTMXRequest
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, File
from litestar.status_codes import HTTP_200_OK
from litestar_htmx import HTMXTemplate
from litestar.channels import ChannelsPlugin

from common.exception import SharlyChessException, FormError
from common.i18n import _, ngettext
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.columns.handlers import PlayersTabColumnHandler
from data.columns.players_tab import PlayersTabColumn
from data.event import Event
from data.access_levels.actions import AuthAction
from data.access_levels.client import Client
from data.input_output.data_source import DataSource
from data.input_output.managers import DataSourceManager, PlayerExporterManager
from data.player import Player, PlayerRating, TournamentPlayer
from data.print_documents.documents import (
    PlayerListPrintDocument,
    PlayerCheckinListPrintDocument,
)
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredPlayer
from utils import Utils
from utils.date_time import format_date
from utils.enum import (
    PlayerGender,
    TournamentRating,
    PlayerRatingType,
    PlayerTitle,
    ArbiterTitle,
    Result,
    FormAction,
)
from plugins.manager import plugin_manager
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.guards import (
    EventGuard,
    TournamentActionGuard,
    ActionGuard,
    SetByeGuard,
    PlayerTournamentActionGuard,
)
from web.messages import Message
from web.session import (
    SessionPlayersEvent,
    SessionPlayersSort,
    SessionPlayersSearchResultsId,
    SessionPlayersActiveDataSource,
    SessionPlayersAddOtherActive,
    SessionPlayersHiddenColumns,
    SessionPlayersDisabledColumns,
    SessionPlayersSearch,
    SessionPlayersFilters,
)
from web.utils import SelectOption

logger: Logger = get_logger()


class PlayerAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        player_id: int | None = None,
        tournament_id: int | None = None,
        data_source_id: str | None = None,
        column_id: str | None = None,
        reload_event: bool = False,
    ):
        super().__init__(request, reload_event)
        if self.admin_event is None:
            raise RuntimeError('admin_event not defined')

        self.admin_player: Player | None = None
        if player_id:
            try:
                self.admin_player = self.admin_event.players_by_id[player_id]
            except KeyError:
                raise NotFoundException(f'Player [{player_id}] not found.')

        self.admin_tournament: Tournament | None = None
        if tournament_id:
            try:
                self.admin_tournament = self.admin_event.tournaments_by_id[
                    tournament_id
                ]
            except KeyError:
                raise NotFoundException(f'Tournament [{tournament_id}] not found.')

        self.admin_data_source: DataSource | None = None
        if data_source_id:
            try:
                self.admin_data_source = DataSourceManager().get_object(data_source_id)
            except KeyError:
                raise NotFoundException(f'Unknown data source [{data_source_id}].')
        self.admin_column: PlayersTabColumn | None = None
        if column_id:
            self.admin_column = self.column_handler.get_column(column_id)
            if not self.admin_column:
                raise NotFoundException(f'Unknown column [{column_id}].')
        self._filter_values_set = False

    def get_admin_tournament(self) -> Tournament:
        assert self.admin_tournament is not None
        return self.admin_tournament

    def get_admin_player(self) -> Player:
        assert self.admin_player is not None
        return self.admin_player

    def get_admin_data_source(self) -> DataSource:
        assert self.admin_data_source is not None
        return self.admin_data_source

    def get_admin_column(self) -> PlayersTabColumn:
        assert self.admin_column is not None
        return self.admin_column

    @cached_property
    def allowed_tournaments(self) -> list[Tournament]:
        return self.client.allowed_tournaments_for_action(AuthAction.VIEW_PLAYERS_TAB)

    @property
    def player_addable_tournaments(self):
        return [
            tournament
            for tournament in self.allowed_tournaments
            if tournament.can_add_players
        ]

    @cached_property
    def column_handler(self) -> PlayersTabColumnHandler:
        event = self.get_admin_event()
        handler = PlayersTabColumnHandler(event)
        hidden_column_ids = SessionPlayersHiddenColumns(
            self.request, event.uniq_id
        ).get()
        disabled_column_ids = SessionPlayersDisabledColumns(
            self.request, event.uniq_id
        ).get()
        handler.set_column_states(disabled_column_ids, hidden_column_ids)
        return handler

    def set_column_filter_values(self, override: bool = False):
        if override or self._filter_values_set:
            return
        event = self.get_admin_event()
        allowed_players = list(self.client.allowed_players)
        filter_keys_by_column_id = SessionPlayersFilters(
            self.request, event.uniq_id
        ).get()
        for column in self.column_handler.visible_columns:
            if not column.is_filtrable:
                continue
            column.set_filter_values(
                allowed_players,
                event,
                active_keys=filter_keys_by_column_id.get(column.id, []),
            )
        self._filter_values_set = True

    @cached_property
    def carry_over_fields(self) -> list[str]:
        fields = [
            'tournament_id',
            'mail',
            'phone',
            'comment',
            'owed',
            'paid',
            'fixed',
        ]
        plugin_manager.hook_for_event(
            self.get_admin_event(), 'insert_player_form_carry_over_field'
        )(fields=fields)
        return fields

    @property
    def default_print_document(self) -> str:
        print_tournament_ids = self.default_tournament_for_print_modal(
            tournament_id=None
        )
        tournaments = list(self.allowed_tournaments)
        if print_tournament_ids:
            tournaments = [
                tournament
                for tournament in tournaments
                if tournament.id in print_tournament_ids
            ]
        check_in_open = all(tournament.check_in_open for tournament in tournaments)
        return (
            PlayerCheckinListPrintDocument.static_id()
            if check_in_open
            else PlayerListPrintDocument.static_id()
        )

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_event_tab': 'admin-event-players-tab',
            'admin_player': self.admin_player,
            'admin_tournament': self.admin_tournament,
        }


class PlayerAdminController(BaseEventAdminController):
    PAGE_SIZE = 25
    search_results_by_session: dict[int, list[int]] = {}

    guards = [
        EventGuard(),
        ActionGuard(AuthAction.VIEW_PLAYERS_TAB),
    ]

    @classmethod
    def filtered_players(
        cls, web_context: PlayerAdminWebContext, players: Iterable[Player]
    ) -> list[Player]:
        request = web_context.request
        event = web_context.get_admin_event()
        handler = web_context.column_handler
        web_context.set_column_filter_values()
        search = normalized_key(SessionPlayersSearch(request, event.uniq_id).get())
        session_filters = SessionPlayersFilters(request, event.uniq_id)
        if search:
            search_key_getters: list[Callable[[Player], str]] = [
                column.get_search_key for column in handler.searchable_columns
            ]
            players = [
                player
                for player in players
                if cls._matches_string_search(
                    search, ' '.join(getter(player) for getter in search_key_getters)
                )
            ]
        getters_active_keys: list[tuple[Callable[[Player], str], list[str]]] = []
        for column_id, filter_keys in session_filters.get().items():
            column = handler.get_column(column_id)
            if not column or not column.is_visible:
                session_filters.set_column_filters(column_id, [])
                continue
            active_keys = [
                filter_value.key
                for filter_value in column.filter_values
                if filter_value.is_active
            ]
            if len(active_keys) in (len(column.filter_values), 0):
                continue
            getters_active_keys.append((column.get_filter_key, active_keys))
        return [
            player
            for player in players
            if all(
                key_getter(player) in active_keys
                for key_getter, active_keys in getters_active_keys
            )
        ]

    @staticmethod
    def _matches_string_search(search: str, match: str):
        search_parts = set(search.split(' '))
        match_str = normalized_key(match)
        return all(search_part in match_str for search_part in search_parts)

    @staticmethod
    def _default_player_sort_key_function(_player: Player) -> tuple:
        return tuple()

    @classmethod
    def sorted_player_ids(
        cls, web_context: PlayerAdminWebContext, players: list[Player]
    ) -> list[int]:
        request = web_context.request
        event = web_context.get_admin_event()
        sort_column, is_asc = SessionPlayersSort(request, event.uniq_id).get()
        column = web_context.column_handler.get_column(sort_column)
        sort_key_function = (
            column.sort_key_function
            if column
            else cls._default_player_sort_key_function
        )
        sorted_players = sorted(
            players,
            key=lambda player: (
                sort_key_function(player) + (player.last_name, player.first_name)
            ),
            reverse=not is_asc,
        )
        return [player.id for player in sorted_players]

    @classmethod
    def get_search_results(cls, web_context: PlayerAdminWebContext):
        request = web_context.request
        event = web_context.get_admin_event()
        session_event_uniq_id = SessionPlayersEvent(request).get()
        search_results_id = SessionPlayersSearchResultsId(request).get()
        if (
            search_results_id is None
            or session_event_uniq_id != event.uniq_id
            or search_results_id not in cls.search_results_by_session
        ):
            return cls.set_players_search_results(web_context)
        return cls.search_results_by_session[search_results_id]

    @classmethod
    def set_players_search_results(
        cls, web_context: PlayerAdminWebContext
    ) -> list[int]:
        request = web_context.request
        event = web_context.get_admin_event()
        filtered_players = cls.filtered_players(
            web_context, web_context.client.allowed_players
        )
        search_results = cls.sorted_player_ids(web_context, filtered_players)
        results_session_id = SessionPlayersSearchResultsId(request).get()
        if not results_session_id:
            results_session_id = max([0] + list(cls.search_results_by_session)) + 1
            SessionPlayersSearchResultsId(request).set(results_session_id)
        cls.search_results_by_session[results_session_id] = search_results
        SessionPlayersEvent(request).set(event.uniq_id)
        return search_results

    @classmethod
    def set_disabled_columns(cls, web_context: PlayerAdminWebContext):
        request = web_context.request
        event = web_context.get_admin_event()
        handler = web_context.column_handler
        allowed_tournaments = web_context.allowed_tournaments
        allowed_players = list(web_context.client.allowed_players)
        disabled_column_ids = [
            column.id
            for column in handler.columns
            if not column.is_enabled_for_tournaments(allowed_tournaments)
            or not column.is_enabled_for_players(allowed_players)
        ]
        SessionPlayersDisabledColumns(request, event.uniq_id).set(disabled_column_ids)
        handler.set_column_states(
            disabled_column_ids,
            SessionPlayersHiddenColumns(request, event.uniq_id).get(),
        )

    @classmethod
    def delete_from_search_results(cls, request: HTMXRequest, player_id: int):
        results_session_id = SessionPlayersSearchResultsId(request).get()
        if not results_session_id:
            return
        try:
            cls.search_results_by_session[results_session_id].remove(player_id)
        except ValueError:
            pass

    # -------------------------------------------------------------------------
    # Tab
    # -------------------------------------------------------------------------

    @classmethod
    def _player_table_header_context(
        cls, web_context: PlayerAdminWebContext
    ) -> dict[str, Any]:
        request = web_context.request
        event = web_context.get_admin_event()
        web_context.set_column_filter_values()
        sort_column, is_sort_asc = SessionPlayersSort(request, event.uniq_id).get()
        search_results = cls.get_search_results(web_context)
        allowed_players = list(web_context.client.allowed_players)
        return {
            'nav_tab_title': _('Players ({num})').format(num=len(allowed_players)),
            'allowed_players': allowed_players,
            'filtered_player_count': len(search_results),
            'sort_column': sort_column,
            'is_sort_asc': is_sort_asc,
            'is_search_active': len(allowed_players) > len(search_results),
        }

    @classmethod
    def _player_table_page_context(
        cls, web_context: PlayerAdminWebContext, page: int = 1
    ) -> dict[str, Any]:
        search_results = cls.get_search_results(web_context)
        pages = math.ceil(len(search_results) / cls.PAGE_SIZE)
        start_index = ((page or 1) - 1) * cls.PAGE_SIZE
        end_index = (page or 1) * cls.PAGE_SIZE
        allowed_players_by_id = web_context.client.allowed_players_by_id
        players_by_index: dict[int, Player] = {}
        for index, player_id in enumerate(search_results[start_index:end_index]):
            if player := allowed_players_by_id.get(player_id, None):
                players_by_index[start_index + index + 1] = player
        template_context = {
            'players_by_index': players_by_index,
            'page': page,
            'pages': pages,
        }
        return template_context | cls._player_table_row_context(web_context)

    @classmethod
    def _player_table_row_context(
        cls, web_context: PlayerAdminWebContext
    ) -> dict[str, Any]:
        return {
            'columns': web_context.column_handler.columns,
            'visible_columns': web_context.column_handler.visible_columns,
            'player_addable_tournaments': web_context.player_addable_tournaments,
            'federations': SharlyChessConfig().federations,
        }

    @classmethod
    def _render_players_tab(cls, web_context: PlayerAdminWebContext) -> HTMXTemplate:
        request = web_context.request
        event = web_context.get_admin_event()
        cls.set_disabled_columns(web_context)
        cls.set_players_search_results(web_context)
        template_context = (
            web_context.template_context
            | cls._player_table_header_context(web_context)
            | cls._player_table_page_context(web_context)
        )
        searchable_column_names = [
            column.name for column in web_context.column_handler.searchable_columns
        ]
        template_context |= {
            'default_print_document': web_context.default_print_document,
            'data_sources': DataSourceManager().objects(),
            'search': SessionPlayersSearch(request, event.uniq_id).get(),
            'allowed_tournaments': web_context.allowed_tournaments,
            'enabled_columns': web_context.column_handler.enabled_columns,
            'searchable_column_names': searchable_column_names,
            'player_exporters': PlayerExporterManager().objects(),
        }
        return cls._admin_base_event_render(template_context)

    @classmethod
    def _render_players_table(cls, web_context: PlayerAdminWebContext) -> HTMXTemplate:
        cls.set_players_search_results(web_context)
        template_context = (
            web_context.template_context
            | cls._player_table_header_context(web_context)
            | cls._player_table_page_context(web_context)
        )
        return HTMXTemplate(
            template_name='/admin/players/table/table.html',
            re_swap='outerHTML',
            re_target='#players-table',
            context=web_context.template_context | template_context,
        )

    @classmethod
    def _render_player_table_row(
        cls,
        web_context: PlayerAdminWebContext,
        deleted_player_id: int | None = None,
    ) -> HTMXTemplate:
        template_context = (
            web_context.template_context
            | cls._player_table_header_context(web_context)
            | cls._player_table_row_context(web_context)
        )
        admin_player = web_context.admin_player
        search_results = cls.get_search_results(web_context)
        if admin_player and not deleted_player_id:
            if cls.filtered_players(web_context, [admin_player]):
                index = (
                    search_results.index(admin_player.id) + 1
                    if admin_player.id in search_results
                    else None
                )
                template_context |= {
                    'updated_player': admin_player,
                    'index': index,
                }
            else:
                deleted_player_id = admin_player.id
        if deleted_player_id:
            if deleted_player_id in search_results:
                search_results.remove(deleted_player_id)
        template_context |= {'deleted_player_id': deleted_player_id}
        return HTMXTemplate(
            template_name='/admin/players/table/header_and_row.html',
            context=template_context,
            re_target='#modal-wrapper',
            trigger_event='renumber_players_and_close_modal',
            after='settle',
        )

    @get(
        path='/event/{event_uniq_id:str}/players',
        name='admin-event-players-tab',
    )
    async def htmx_admin_event_players_tab(self, request: HTMXRequest) -> Template:
        return self._render_players_tab(PlayerAdminWebContext(request))

    @get(
        path='/event/{event_uniq_id:str}/players/columns',
        name='admin-event-players-columns',
    )
    async def htmx_admin_event_players_columns(
        self, request: HTMXRequest, column_ids: list[str]
    ) -> Template:
        web_context = PlayerAdminWebContext(request)
        event = web_context.get_admin_event()
        handler = web_context.column_handler
        disabled_column_ids = SessionPlayersDisabledColumns(
            request, event.uniq_id
        ).get()
        session_hidden = SessionPlayersHiddenColumns(request, event.uniq_id)
        current_hidden_column_ids = session_hidden.get() or []
        hidden_column_ids: list[str] = []
        for column in handler.columns:
            if not column.is_hideable or column.id in column_ids:
                continue
            # Keep hidden the disabled columns that have manually been hidden by the user
            # Preserve the other ones, which will appear if they become enabled
            if (
                column.id in disabled_column_ids
                and column.id not in current_hidden_column_ids
            ):
                continue
            hidden_column_ids.append(column.id)
        session_hidden.set(hidden_column_ids)

        session_filters = SessionPlayersFilters(request, event.uniq_id)
        filters = session_filters.get()
        for column_id in column_ids:
            if column_id in filters:
                del filters[column_id]
        session_filters.set(filters)
        self.set_disabled_columns(web_context)
        return self._render_players_tab(web_context)

    @get(
        path='/event/{event_uniq_id:str}/players/set-filter/{column_id:str}',
        name='admin-event-players-set-filter',
    )
    async def htmx_admin_event_players_set_filter(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        column_id: str,
        filters: list[str],
    ) -> Template:
        web_context = PlayerAdminWebContext(request, column_id=column_id)
        event = web_context.get_admin_event()
        column = web_context.get_admin_column()
        if not column.is_filtrable:
            raise ClientException(f'Column [{column.id}] not filtrable')
        filter_keys: list[str] = []
        for filter_key in filters[1:]:
            try:
                column.get_filter_value_from_key(filter_key, event)
                filter_keys.append(filter_key)
            except ValueError:
                logger.error(
                    f'Invalid filter key [{filter_key}] for column [{column.id}].'
                )
        SessionPlayersFilters(request, event_uniq_id).set_column_filters(
            column_id, filter_keys
        )
        return self._render_players_table(web_context)

    @get(
        path='/event/{event_uniq_id:str}/players/sort/{column_id:str}',
        name='admin-event-players-sort',
    )
    async def htmx_admin_event_players_sort(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        column_id: str,
    ) -> Template:
        web_context = PlayerAdminWebContext(request, column_id=column_id)
        column = web_context.get_admin_column()
        session_sort = SessionPlayersSort(request, event_uniq_id)
        current_column_id, current_is_asc = session_sort.get()
        if current_column_id != column.id:
            sort_column_id = column.id
            is_asc = True
        elif current_is_asc:
            sort_column_id = column.id
            is_asc = False
        else:
            sort_column_id = ''
            is_asc = True
        session_sort.set((sort_column_id, is_asc))
        return self._render_players_table(web_context)

    @get(
        path='/event/{event_uniq_id:str}/players/search',
        name='admin-event-players-search',
    )
    async def htmx_admin_event_players_search(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        search: str | None = None,
    ) -> Template:
        web_context = PlayerAdminWebContext(request)
        SessionPlayersSearch(request, event_uniq_id).set(search)
        return self._render_players_table(web_context)

    @get(
        path='/event/{event_uniq_id:str}/players/clear-filters',
        name='admin-event-players-clear-filters',
    )
    async def htmx_admin_event_players_clear_filters(
        self, request: HTMXRequest, event_uniq_id: str
    ) -> Template:
        web_context = PlayerAdminWebContext(request)
        SessionPlayersSearch(request, event_uniq_id).unset()
        SessionPlayersFilters(request, event_uniq_id).unset()
        SessionPlayersSearch(request, event_uniq_id).unset()
        SessionPlayersSort(request, event_uniq_id).unset()
        return self._render_players_tab(web_context)

    @get(
        path='/event/{event_uniq_id:str}/players/{page:int}',
        name='admin-event-players-page',
    )
    async def htmx_admin_event_players_page(
        self, request: HTMXRequest, page: int
    ) -> Template:
        web_context = PlayerAdminWebContext(request)
        template_context = self._player_table_page_context(web_context, page)
        return HTMXTemplate(
            template_name='/admin/players/table/page.html',
            context=web_context.template_context | template_context,
        )

    @get(
        path='/player-row/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-row',
    )
    async def htmx_admin_player_row(
        self, request: HTMXRequest, player_id: int
    ) -> Template:
        return self._render_player_table_row(PlayerAdminWebContext(request, player_id))

    # -------------------------------------------------------------------------
    # Player Modal
    # -------------------------------------------------------------------------

    @staticmethod
    def _get_gender_options() -> dict[str, str]:
        return {
            WebContext.value_to_form_data(gender.value): gender.name
            for gender in PlayerGender
        }

    @classmethod
    def _render_players_form_modal(
        cls,
        web_context: PlayerAdminWebContext,
        action: FormAction,
        old_player_id: int | None = None,
        search_stored_player: StoredPlayer | None = None,
        data: dict[str, str] | None = None,
        carry_over_data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
        warning_message: str | None = None,
    ) -> Template:
        request = web_context.request
        event = web_context.get_admin_event()
        admin_player = web_context.admin_player
        template_context = web_context.template_context
        allowed_players_by_id = web_context.client.allowed_players_by_id

        if data is None:
            first_name: str | None = None
            last_name: str | None = None
            date_of_birth: str | None = None
            gender = PlayerGender.NONE.value
            ratings: dict[TournamentRating, PlayerRating] = {
                tr: PlayerRating(estimated=0) for tr in TournamentRating
            }
            title = PlayerTitle.NONE.value
            federation = event.federation
            club: str | None = None
            fide_id: int | None = None
            mail: str | None = None
            phone: str | None = None
            comment: str | None = None
            owed: float = 0.0
            paid: float = 0.0
            fixed: int | None = None
            stored_plugin_data: dict[str, dict[str, Any]] = {}
            stored_player = search_stored_player
            tournament_id: int | None = None
            if not stored_player and admin_player:
                stored_player = admin_player.stored_player
            if stored_player:
                if search_stored_player or action != FormAction.REPLACE:
                    first_name = stored_player.first_name
                    last_name = stored_player.last_name
                    gender = stored_player.gender
                    date_of_birth = WebContext.value_to_date_form_data(
                        stored_player.date_of_birth
                    )
                    if stored_player.year_of_birth:
                        date_of_birth = str(stored_player.year_of_birth)
                    for tr_value, rating in stored_player.ratings.items():
                        ratings[TournamentRating(tr_value)] = (
                            PlayerRating.from_stored_value(rating)
                        )
                    title = stored_player.title
                    federation = stored_player.federation
                    club = stored_player.club
                    fide_id = stored_player.fide_id or None
                # Fields unused by the search, kept on replace
                mail = stored_player.mail
                phone = stored_player.phone
                comment = stored_player.comment
                owed = stored_player.owed
                paid = stored_player.paid
                fixed = stored_player.fixed
                stored_plugin_data = stored_player.plugin_data
            if action == FormAction.CREATE:
                if len(event.not_finished_tournaments_sorted_by_index) == 1:
                    tournament_id = event.not_finished_tournaments_sorted_by_index[0].id
            else:
                assert admin_player is not None
                tournament_id = admin_player.single_tournament.id

            rating_data: dict[str, Any] = {}
            for tournament_rating in TournamentRating:
                rating_ = ratings[tournament_rating]
                key = tournament_rating.form_key
                rating_data |= {
                    f'{key}_rating_fide': rating_.fide or None,
                    f'{key}_rating_national': rating_.national or None,
                    f'{key}_rating_estimated': rating_.estimated or None,
                }

            plugin_form_data: dict[str, str] = {}
            for (
                plugin_id,
                plugin_data_class,
            ) in Player.plugin_data_class_by_plugin_id().items():
                plugin_form_data |= plugin_data_class.from_stored_value(
                    stored_plugin_data.get(plugin_id, {})
                ).to_form_data(action=action if not search_stored_player else None)

            data = WebContext.values_dict_to_form_data(
                {
                    'last_name': last_name,
                    'first_name': first_name,
                    'gender': gender,
                    'tournament_id': tournament_id,
                    'title': title,
                    'federation': federation,
                    'fide_id': fide_id,
                    'club': club,
                    'mail': mail,
                    'phone': phone,
                    'comment': comment,
                    'owed': owed,
                    'paid': paid,
                    'fixed': fixed or None,
                    'date_of_birth': date_of_birth,
                }
                | rating_data
                | plugin_form_data
                | (carry_over_data or {})
            )
        if errors is None:
            errors = {}
        tournaments = web_context.player_addable_tournaments
        tournament_options: dict[str, str] = {}
        if action == FormAction.CREATE:
            # force the choice of the tournament on player creation if several tournaments
            if len(tournaments) > 1:
                tournament_options |= {'': '-'}
        else:
            assert admin_player is not None
            if admin_player.single_tournament not in tournaments:
                tournaments.insert(0, admin_player.single_tournament)
        tournament_options |= web_context.get_tournament_options(tournaments)
        plugin_templates_by_section: dict[str, list[str]] = defaultdict(list)
        plugin_manager.hook_for_event(event, 'insert_player_form_fields_template')(
            templates_by_section=plugin_templates_by_section
        )
        template_context |= {
            'gender_options': cls._get_gender_options(),
            'tournament_ratings_strings': {
                TournamentRating.STANDARD: {
                    'label': _('Standard:'),
                    'help': _(
                        'The rating used when the time control is at least 60 minutes.'
                    ),
                },
                TournamentRating.RAPID: {
                    'label': _('Rapid:'),
                    'help': _(
                        'The rating used when the time control is more than 10 minutes and less than 60 minutes.'
                    ),
                },
                TournamentRating.BLITZ: {
                    'label': _('Blitz:'),
                    'help': _(
                        'The rating used when the time control is at most 10 minutes.'
                    ),
                },
            },
            'rating_type_labels': {
                'fide': PlayerRatingType.FIDE.short_name,
                'national': PlayerRatingType.NATIONAL.short_name,
                'estimated': PlayerRatingType.ESTIMATED.short_name,
            },
            'title_options': {
                str(t.value): f'{t.short_name} - {t.name}'
                if t.short_name
                else f'{t.name}'
                for t in PlayerTitle
            },
            'federation_options': cls._get_federation_options(),
            'tournament_options': tournament_options,
            'selected_data_source': SessionPlayersActiveDataSource(request).get(),
            'data_source_options': DataSourceManager().options(),
            'plugin_templates_by_section': plugin_templates_by_section,
            'previous_player': (
                allowed_players_by_id.get(old_player_id, None)
                if action == 'create' and old_player_id
                else None
            ),
            'data_sources': DataSourceManager().objects(),
            'warning_message': warning_message,
            'add_other_active': SessionPlayersAddOtherActive(request).get(),
            'modal': 'player',
            'action': action,
            'data': data,
            'errors': errors,
        }
        template_context |= Utils.concat_dicts(
            plugin_manager.hook_for_event(event, 'get_player_form_template_context')(
                web_context=web_context
            )
        )
        return cls._admin_base_event_render(template_context)

    @get(
        path='/player-modal/create/{event_uniq_id:str}',
        name='admin-player-create-modal',
    )
    async def htmx_admin_player_create_modal(self, request: HTMXRequest) -> Template:
        return self._render_players_form_modal(
            PlayerAdminWebContext(request), FormAction.CREATE
        )

    @post(
        path=[
            '/player-modal/from-search/{event_uniq_id:str}/'
            '{data_source_id:str}/{player_source_id:str}',
            '/player-modal/create-from-search/{event_uniq_id:str}/'
            '/{data_source_id:str}/{player_source_id:str}',
        ],
        name='admin-player-modal-from-search',
    )
    async def htmx_admin_player_modal_create_from_search(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        data_source_id: str,
        player_source_id: str,
    ) -> Template:
        player_id = WebContext.form_data_to_int(data, 'player_id')
        web_context = PlayerAdminWebContext(
            request, player_id, data_source_id=data_source_id
        )
        data_source = web_context.get_admin_data_source()
        errors: dict[str, str] = {}
        stored_player: StoredPlayer | None = None
        if not data_source.is_available:
            raise ClientException(f'Data source [{data_source_id}] is not available.')
        try:
            stored_player = await data_source.fetch_player(
                player_source_id=player_source_id,
                augment_arbiter_title=False,
            )
            if not stored_player:
                raise NotFoundException(
                    f'Player [{player_source_id}] unexpectedly '
                    f'not found in data source [{data_source_id}]'
                )
        except SharlyChessException:
            errors[data_source.search_element_name] = _(
                'Connection to the data source [{data_source}] failed. '
                'Consult the logs for more details.'
            ).format(data_source=data_source_id)
        return self._render_players_form_modal(
            web_context,
            action=FormAction.REPLACE if player_id else FormAction.CREATE,
            search_stored_player=stored_player,
            carry_over_data={
                field: str(data.get(field, ''))
                for field in web_context.carry_over_fields
            },
            errors=errors,
        )

    @get(
        path='/player-modal/{action:str}/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-modal',
        guards=[PlayerTournamentActionGuard(AuthAction.UPDATE_PLAYERS)],
    )
    async def htmx_admin_player_modal(
        self,
        request: HTMXRequest,
        action: str,
        player_id: int,
    ) -> Template:
        web_context = PlayerAdminWebContext(request, player_id)
        return self._render_players_form_modal(web_context, FormAction(action))

    @get(
        path='/player-delete-modal/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-delete-modal',
        guards=[PlayerTournamentActionGuard(AuthAction.UPDATE_PLAYERS)],
    )
    async def htmx_admin_player_delete_modal(
        self,
        request: HTMXRequest,
        player_id: int,
    ) -> Template:
        web_context = PlayerAdminWebContext(request, player_id)
        return self._admin_base_event_render(
            web_context.template_context | {'modal': 'player-delete'}
        )

    @classmethod
    def _validate_player_form_data(
        cls,
        web_context: PlayerAdminWebContext,
        action: FormAction,
        data: dict[str, str],
    ) -> dict[str, str]:
        event = web_context.get_admin_event()
        errors: dict[str, str] = {}
        tournament: Tournament | None = None
        field = 'tournament_id'
        try:
            tournament_id = WebContext.form_data_to_int(data, field)
            if not tournament_id:
                raise ValueError('Tournament ID not supplied')
            tournament = event.tournaments_by_id[tournament_id]
        except (ValueError, KeyError):
            errors[field] = _('Please choose the tournament.')
        player: Player | None = None
        if action != FormAction.CREATE and tournament is not None:
            player = web_context.get_admin_player()
            if tournament.id != player.single_tournament.id:
                try:
                    cls._validate_player_tournament_move(
                        event,
                        player,
                        player.single_tournament,
                        tournament,
                    )
                except ValueError as e:
                    errors[field] = str(e)

        last_name = WebContext.form_data_to_str(data, field := 'last_name')
        if not last_name:
            errors[field] = _('This field is required.')
        first_name = WebContext.form_data_to_str(data, 'first_name')
        date_of_birth: date | None = None
        try:
            date_of_birth = WebContext.form_data_to_date(data, field := 'date_of_birth')
        except FormError:
            year_str = data.get(field, '')
            if year_str:
                if not year_str.isdigit() or len(year_str) != 4:
                    errors[field] = _(
                        'Invalid date format (expected: {format}).'
                    ).format(
                        format=_('YYYY or {date_format}').format(
                            date_format=SharlyChessConfig().date_formatter.name
                        ),
                    )
        try:
            if value := WebContext.form_data_to_str(data, field := 'gender'):
                PlayerGender(value)
        except ValueError:
            # should never happen, not translated.
            errors[field] = f'Invalid gender value [{data[field]}].'
            data[field] = ''
        try:
            if value := WebContext.form_data_to_str(data, field := 'title'):
                PlayerTitle(value)
        except ValueError:
            # should never happen, not translated.
            errors[field] = f'Invalid title value [{data[field]}].'
            data[field] = ''
        federation = WebContext.form_data_to_str(data, field := 'federation', '')
        if federation not in SharlyChessConfig().federations:
            # should never happen, not translated.
            errors[field] = f'Invalid federation value [{data[field]}].'
            data[field] = ''
        fide_id: int | None = None
        try:
            fide_id = WebContext.form_data_to_int(data, field := 'fide_id', minimum=1)
        except ValueError:
            errors[field] = _('Invalid FIDE ID [{fide_id}].').format(
                fide_id=data[field]
            )
        try:
            WebContext.form_data_to_mail(data, field := 'mail')
        except ValueError:
            errors[field] = _('Invalid mail [{mail}].').format(mail=data[field])
        try:
            WebContext.form_data_to_float(data, field := 'owed')
        except ValueError:
            errors[field] = _('Invalid amount [{amount}].').format(amount=data[field])
        try:
            WebContext.form_data_to_float(data, field := 'paid')
        except ValueError:
            errors[field] = _('Invalid amount [{amount}].').format(amount=data[field])
        try:
            WebContext.form_data_to_int(data, field := 'fixed', minimum=1)
        except ValueError:
            errors[field] = _('Invalid fixed board number [{fixed_board}].').format(
                fixed_board=data[field]
            )
        if tournament and (fide_id or date_of_birth):
            for tournament_player in tournament.tournament_players:
                if player and tournament_player.id == player.id:
                    continue
                if fide_id and tournament_player.fide_id == fide_id:
                    errors['fide_id'] = _(
                        'Player with FIDE ID [{fide_id}] '
                        'already plays tournament [{tournament}].'
                    ).format(fide_id=fide_id, tournament=tournament.name)
                if (
                    date_of_birth
                    and tournament_player.last_name == last_name
                    and tournament_player.first_name == first_name
                    and tournament_player.date_of_birth == date_of_birth
                ):
                    errors['last_name'] = _(
                        'Player [{player}] already plays tournament [{tournament}].'
                    ).format(
                        player=f'{tournament_player.full_name} {format_date(date_of_birth)}',
                        tournament=tournament.name,
                    )
        plugin_manager.hook_for_event(event, 'validate_player_form_fields')(
            action=action,
            tournament=tournament,
            player=player,
            data=data,
            errors=errors,
        )
        return errors

    @classmethod
    def _stored_player_from_data(cls, data: dict[str, str]) -> StoredPlayer:
        date_of_birth: date | None = None
        year_of_birth: int | None = None
        field = 'date_of_birth'
        try:
            date_of_birth = WebContext.form_data_to_date(data, field)
        except FormError:
            year_of_birth = WebContext.form_data_to_int(data, field)
        return StoredPlayer(
            id=None,
            first_name=(WebContext.form_data_to_str(data, 'first_name') or '').title(),
            last_name=(WebContext.form_data_to_str(data, 'last_name') or '').upper(),
            date_of_birth=date_of_birth,
            year_of_birth=year_of_birth,
            gender=WebContext.form_data_to_str(data, 'gender')
            or PlayerGender.NONE.value,
            mail=WebContext.form_data_to_str(data, 'mail'),
            phone=WebContext.form_data_to_str(data, 'phone'),
            comment=data.get('comment'),
            owed=WebContext.form_data_to_float(data, 'owed') or 0.0,
            paid=WebContext.form_data_to_float(data, 'paid') or 0.0,
            title=WebContext.form_data_to_str(data, 'title') or PlayerTitle.NONE.value,
            arbiter_title=ArbiterTitle.NONE.value,
            ratings={
                tr.value: PlayerRating(
                    estimated=WebContext.form_data_to_int(
                        data, f'{tr.form_key}_rating_estimated'
                    )
                    or None,
                    national=WebContext.form_data_to_int(
                        data, f'{tr.form_key}_rating_national'
                    )
                    or None,
                    fide=WebContext.form_data_to_int(data, f'{tr.form_key}_rating_fide')
                    or None,
                ).stored_value
                for tr in TournamentRating
            },
            fide_id=WebContext.form_data_to_int(data, 'fide_id'),
            federation=WebContext.form_data_to_str(data, 'federation') or '',
            club=WebContext.form_data_to_str(data, 'club') or '',
            fixed=WebContext.form_data_to_int(data, 'fixed'),
            plugin_data={
                plugin_id: plugin_data_class.from_form_data(data).to_stored_value()
                for plugin_id, plugin_data_class in Player.plugin_data_class_by_plugin_id().items()
            },
        )

    @post(
        path='/player-create/{event_uniq_id:str}',
        name='admin-player-create',
        guard=[TournamentActionGuard(AuthAction.ADD_PLAYERS, search_form=True)],
    )
    async def htmx_admin_player_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = PlayerAdminWebContext(request)
        event = web_context.get_admin_event()
        action = FormAction.CREATE
        add_other = 'add_other' in data
        SessionPlayersAddOtherActive(request).set(add_other)

        errors = self._validate_player_form_data(web_context, action, data)
        if errors:
            return self._render_players_form_modal(
                web_context, action, data=data, errors=errors
            )
        stored_player = self._stored_player_from_data(data)
        tournament_id = WebContext.form_data_to_int(data, 'tournament_id') or 0
        tournament = event.tournaments_by_id[tournament_id]
        player_id = event.add_player(stored_player, [tournament])
        self.set_players_search_results(web_context)
        player = tournament.tournament_players_by_id[player_id]
        warning_message: str | None = None
        if not tournament.player_matches_criteria(player.single_tournament_player):
            warning_message = _(
                'Player [{player}] has been created, but '
                'does not match tournament criteria: {names}'
            ).format(
                player=player.full_name,
                names=player.single_tournament.failing_criteria_message(
                    player.single_tournament_player
                ),
            )

        if add_other:
            return self._render_players_form_modal(
                web_context,
                FormAction.CREATE,
                old_player_id=player_id,
                warning_message=warning_message,
                carry_over_data={
                    field: str(data.get(field, ''))
                    for field in web_context.carry_over_fields
                },
            )
        if warning_message:
            Message.warning(request, warning_message)
        else:
            Message.success(
                request,
                _('Player [{player}] has been created.').format(
                    player=player.full_name
                ),
            )
        return self._render_players_tab(web_context)

    def _update_player(
        self,
        web_context: PlayerAdminWebContext,
        data: dict[str, str],
        action: FormAction,
    ) -> Template:
        request = web_context.request
        event = web_context.get_admin_event()
        errors = self._validate_player_form_data(web_context, action, data)
        if errors:
            return self._render_players_form_modal(
                web_context, action, data=data, errors=errors
            )
        stored_player = self._stored_player_from_data(data)
        tournament_id = WebContext.form_data_to_int(data, 'tournament_id') or 0
        tournament = event.tournaments_by_id[tournament_id]
        player = web_context.get_admin_player()
        event.update_player(player, stored_player)
        previous_tournament = player.single_tournament
        if tournament.id != previous_tournament.id:
            event.move_player_to_tournament(player, tournament)
        web_context = PlayerAdminWebContext(request, player.id, reload_event=True)
        return self._render_player_table_row(web_context)

    @patch(
        path='/player-update/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-update',
        guard=[
            TournamentActionGuard(AuthAction.UPDATE_PLAYERS, search_form=True),
            PlayerTournamentActionGuard(AuthAction.UPDATE_PLAYERS),
        ],
    )
    async def htmx_admin_player_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        player_id: int,
    ) -> Template:
        return self._update_player(
            PlayerAdminWebContext(request, player_id), data, FormAction.UPDATE
        )

    @patch(
        path='/player-replace/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-replace',
        guard=[
            TournamentActionGuard(AuthAction.UPDATE_PLAYERS, search_form=True),
            PlayerTournamentActionGuard(AuthAction.UPDATE_PLAYERS),
        ],
    )
    async def htmx_admin_player_replace(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        player_id: int,
    ) -> Template:
        return self._update_player(
            PlayerAdminWebContext(request, player_id), data, FormAction.UPDATE
        )

    @delete(
        path='/player-delete/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-delete',
        guard=[PlayerTournamentActionGuard(AuthAction.DELETE_PLAYERS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_player_delete(
        self, request: HTMXRequest, player_id: int
    ) -> Template:
        web_context = PlayerAdminWebContext(request, player_id)
        player = web_context.get_admin_player()
        tournament = player.single_tournament
        event = web_context.get_admin_event()
        deleted_player_id: int | None = None
        if player.single_tournament_player.has_real_pairings:
            Message.error(
                request,
                _(
                    'Player [{player}] has pairings in tournament [{tournament}].'
                ).format(
                    player=player.full_name,
                    tournament=tournament.name,
                ),
            )
        else:
            event.delete_player(player.id)
            deleted_player_id = player.id
        return self._render_player_table_row(
            web_context, deleted_player_id=deleted_player_id
        )

    # -------------------------------------------------------------------------
    # Record modal
    # -------------------------------------------------------------------------

    @staticmethod
    def _get_bye_options(
        client: Client, tournament_player: TournamentPlayer, round_: int
    ) -> dict[str, SelectOption]:
        tournament = tournament_player.tournament
        hpb_disabled_message: str | None = None
        fpb_disabled_message: str | None = None
        if not client.can_set_half_point_bye(tournament.id):
            hpb_disabled_message = _('You are not allowed to set Half-Point Byes.')
        if not client.can_set_full_point_bye(tournament.id):
            fpb_disabled_message = _('You are not allowed to set Full-Point Byes.')
        current_byes = tournament_player.byes_count
        if current_byes + 1 > tournament.max_byes:
            hpb_disabled_message = _(
                'Not enough byes available to set a Half-Point Bye (required: 1).'
            )
        if current_byes + 2 > tournament.max_byes:
            fpb_disabled_message = _(
                'Not enough byes available to set a Full-Point Bye (required: 2).'
            )
        if round_ > tournament.rounds - tournament.last_rounds_no_byes:
            message = ngettext(
                "Byes can't be set for the last round of the tournament.",
                "Byes can't be set for the last {rounds} rounds of the tournament.",
                tournament.last_rounds_no_byes,
            ).format(rounds=tournament.last_rounds_no_byes)
            hpb_disabled_message = message
            fpb_disabled_message = message
        bye_options: dict[Result, SelectOption] = {
            Result.NO_RESULT: SelectOption(_('Present')),
            Result.ZERO_POINT_BYE: SelectOption(_('Absent')),
            Result.HALF_POINT_BYE: SelectOption(
                _('Half-Point Bye'),
                tooltip=hpb_disabled_message,
                disabled=bool(hpb_disabled_message),
            ),
            Result.FULL_POINT_BYE: SelectOption(
                _('Full-Point Bye (deprecated)'),
                tooltip=fpb_disabled_message,
                disabled=bool(fpb_disabled_message),
                classes='' if fpb_disabled_message else 'text-danger',
            ),
        }
        return {
            str(result.value): select_option
            for result, select_option in bye_options.items()
        }

    @classmethod
    def _render_player_records_modal(
        cls, web_context: PlayerAdminWebContext
    ) -> HTMXTemplate:
        player = web_context.get_admin_player()
        tournament = player.single_tournament
        tournament_player = player.single_tournament_player
        data = {
            f'round_{round_}_result': WebContext.value_to_form_data(
                tournament_player.pairings[round_].result.value
            )
            for round_ in range(
                max(1, tournament.current_round),
                tournament.rounds + 1,
            )
        }
        template_context = {
            'get_bye_options': cls._get_bye_options,
            'modal': 'record',
            'data': data,
        }
        return cls._admin_base_event_render(
            web_context.template_context | template_context
        )

    def _set_player_participation(
        self,
        web_context: PlayerAdminWebContext,
        result: Result,
    ) -> Template:
        tournament = web_context.get_admin_tournament()
        player = web_context.get_admin_player()

        # If there aren't any pairings, then the round for the bye is the first round
        round_for_participation = tournament.current_round or 1
        new_byes = {
            round_: result
            for round_ in range(
                round_for_participation,
                tournament.rounds + 1,
            )
            if player.single_tournament_player.pairings[round_].unpaired
        }
        tournament.set_player_byes(player.single_tournament_player, new_byes)

        return self._render_player_records_modal(web_context)

    @get(
        path='/record-modal/{event_uniq_id:str}/{player_id:int}',
        name='admin-record-modal',
        guards=[PlayerTournamentActionGuard(AuthAction.UPDATE_PLAYERS_HISTORY)],
    )
    async def htmx_admin_record_modal(
        self, request: HTMXRequest, player_id: int
    ) -> Template:
        return self._render_player_records_modal(
            PlayerAdminWebContext(request, player_id)
        )

    @patch(
        path=(
            '/withdraw-player/{event_uniq_id:str}/'
            '{tournament_id:int}/{player_id:int}/{round:int}'
        ),
        name='admin-player-withdraw-player',
        guards=[TournamentActionGuard(AuthAction.SET_ZPB)],
    )
    async def htmx_admin_withdraw_player(
        self,
        request: HTMXRequest,
        tournament_id: int,
        player_id: int,
    ) -> Template:
        web_context = PlayerAdminWebContext(request, player_id, tournament_id)
        return self._set_player_participation(web_context, Result.ZERO_POINT_BYE)

    @patch(
        path='/return-player/{event_uniq_id:str}/{tournament_id:int}/{player_id:int}',
        name='admin-player-return-player',
        guards=[TournamentActionGuard(AuthAction.SET_ZPB)],
    )
    async def htmx_admin_return_player(
        self,
        request: HTMXRequest,
        tournament_id: int,
        player_id: int,
    ) -> Template:
        web_context = PlayerAdminWebContext(request, player_id, tournament_id)
        return self._set_player_participation(web_context, Result.NO_RESULT)

    @patch(
        path='/player-set-bye/{event_uniq_id:str}/{player_id:int}/{round:int}',
        name='admin-player-set-bye',
        guard=[SetByeGuard()],
    )
    async def htmx_admin_player_set_bye(
        self,
        request: HTMXRequest,
        player_id: int,
        round: int,
        result: int,
    ) -> Template:
        web_context = PlayerAdminWebContext(request, player_id)
        player = web_context.get_admin_player()
        player.single_tournament.set_player_byes(
            player.single_tournament_player, {round: Result(result)}
        )
        return self._render_player_records_modal(web_context)

    # -------------------------------------------------------------------------
    # Check-in/out
    # -------------------------------------------------------------------------

    @patch(
        path='/tournament-open-check-in/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-open-check-in',
        guard=[TournamentActionGuard(AuthAction.OPEN_CLOSE_CHECK_IN)],
    )
    async def htmx_admin_tournament_open_check_in(
        self, request: HTMXRequest, tournament_id: int
    ) -> Template:
        web_context = PlayerAdminWebContext(request, tournament_id=tournament_id)
        admin_tournament = web_context.get_admin_tournament()
        admin_tournament.open_check_in()
        Message.success(
            request,
            _('Check-in is open for tournament [{tournament}].').format(
                tournament=admin_tournament.name
            ),
        )
        web_context = PlayerAdminWebContext(request, reload_event=True)
        return self._render_players_tab(web_context)

    @get(
        path='/tournament-close-check-in-modal/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-close-check-in-modal',
    )
    async def htmx_tournament_close_check_in_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = PlayerAdminWebContext(request, tournament_id=tournament_id)
        return self._admin_base_event_render(
            web_context.template_context | {'modal': 'close_check_in'}
        )

    @patch(
        path='/tournament-close-check-in/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-close-check-in',
        guard=[ActionGuard(AuthAction.OPEN_CLOSE_CHECK_IN)],
    )
    async def htmx_admin_tournament_close_check_in(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
    ) -> Template:
        web_context = PlayerAdminWebContext(request, tournament_id=tournament_id)
        tournament = web_context.get_admin_tournament()
        action = WebContext.form_data_to_str(data, 'action') or ''
        tournament.close_check_in(
            action == 'zpb-next-round', action == 'zpb-tournament', action == 'delete'
        )
        Message.success(
            request,
            _('Check-in is closed for tournament [{tournament}].').format(
                tournament=tournament.name
            ),
        )
        return HTMXTemplate(
            template_name='common/empty_modal_and_messages.html',
            context={'messages': Message.messages(request)},
            re_target='#modal-wrapper',
            trigger_event='close_modal',
            after='settle',
        )

    @patch(
        path='/player-check-in/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-check-in',
        guard=[PlayerTournamentActionGuard(AuthAction.CHECK_IN_PLAYERS)],
    )
    async def htmx_admin_player_check_in(
        self, request: HTMXRequest, player_id: int
    ) -> Template:
        web_context = PlayerAdminWebContext(request, player_id)
        player = web_context.get_admin_player()
        player.single_tournament.check_in_player(player, check_in=True)
        return self._render_player_table_row(web_context)

    @patch(
        path='/player-check-out/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-check-out',
        guard=[PlayerTournamentActionGuard(AuthAction.CHECK_IN_PLAYERS)],
    )
    async def htmx_admin_player_check_out(
        self,
        request: HTMXRequest,
        player_id: int,
    ) -> Template:
        web_context = PlayerAdminWebContext(request, player_id)
        player = web_context.get_admin_player()
        player.single_tournament.check_in_player(player, check_in=False)
        return self._render_player_table_row(web_context)

    # -------------------------------------------------------------------------
    # Misc
    # -------------------------------------------------------------------------

    @patch(
        path='/player-move/{event_uniq_id:str}/{player_id:int}/{tournament_id:int}',
        name='admin-player-move',
        guard=[
            TournamentActionGuard(AuthAction.UPDATE_PLAYERS),
            PlayerTournamentActionGuard(AuthAction.UPDATE_PLAYERS),
        ],
    )
    async def htmx_admin_player_move(
        self,
        request: HTMXRequest,
        player_id: int,
        tournament_id: int,
    ) -> Template:
        web_context = PlayerAdminWebContext(request, player_id, tournament_id)
        admin_player = web_context.get_admin_player()
        dst_tournament = web_context.get_admin_tournament()
        src_tournament = admin_player.single_tournament
        event = web_context.get_admin_event()
        try:
            self._validate_player_tournament_move(
                event, admin_player, src_tournament, dst_tournament
            )
            event.move_player_to_tournament(admin_player, dst_tournament)
            Message.success(
                request,
                _(
                    'Player [{player}] has been moved '
                    'from tournament [{src_tournament}] '
                    'to tournament [{dst_tournament}].'
                ).format(
                    player=admin_player.full_name,
                    src_tournament=src_tournament.name,
                    dst_tournament=dst_tournament.name,
                ),
            )
        except ValueError as e:
            Message.error(request, str(e))
        web_context = PlayerAdminWebContext(request, player_id, reload_event=True)
        return self._render_player_table_row(web_context)

    @staticmethod
    def _validate_player_tournament_move(
        event: Event,
        player: Player,
        src_tournament: Tournament,
        dst_tournament: Tournament,
    ):
        """Validate that a player can be moved from its current tournament to *dst_tournament*.
        Raises a ValueError if it is not possible."""

        if player.single_tournament_player.has_real_pairings:
            raise ValueError(
                _(
                    'Player [{player}] has pairings in tournament [{tournament}].'
                ).format(
                    player=player.full_name,
                    tournament=src_tournament.name,
                ),
            )
        if not dst_tournament.can_add_players:
            raise ValueError(
                _('Impossible to add players to tournament [{tournament}].').format(
                    tournament=src_tournament.name
                )
            )
        if player.fide_id in dst_tournament.tournament_players_by_fide_id:
            raise ValueError(
                _(
                    'Fide ID [{fide_id}] already present in tournament [{tournament}].'
                ).format(
                    fide_id=player.fide_id,
                    tournament=dst_tournament.name,
                ),
            )
        if plugin_error := (
            plugin_manager.hook_for_event(
                event, 'is_tournament_participation_possible'
            )(
                tournament=dst_tournament,
                tournament_player=player.single_tournament_player,
            )
            or None
        ):
            raise ValueError(plugin_error)

    @get(
        path='/history-popover/{event_uniq_id:str}/{tournament_id:int}/{player_id:int}',
        name='admin-player-history-popover',
    )
    async def htmx_admin_history_popover(
        self, request: HTMXRequest, tournament_id: int, player_id: int
    ) -> Template:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request, player_id, tournament_id
        )

        tournament = web_context.get_admin_tournament()
        tournament.compute_tournament_player_ranks()
        return HTMXTemplate(
            template_name='/admin/players/history_popover.html',
            context=web_context.template_context
            | {
                'player': web_context.get_admin_player(),
            },
        )

    @patch(
        path='/players-update/{event_uniq_id:str}/{data_source_id:str}',
        name='admin-event-players-update',
        guards=[ActionGuard(AuthAction.UPDATE_PLAYERS)],
    )
    async def htmx_admin_update_event_players(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        data_source_id: str,
    ) -> Template:
        web_context = PlayerAdminWebContext(request, data_source_id=data_source_id)
        event = web_context.get_admin_event()
        data_source = web_context.get_admin_data_source()
        flat_data = WebContext.flatten_list_data(data)
        player_ids = WebContext.form_data_to_list_int(flat_data, 'player_ids')
        field_ids = WebContext.form_data_to_list_str(flat_data, 'field_ids')
        fields = [
            field
            for field in data_source.player_updater_fields
            if field.id in field_ids
        ]
        allowed_players_by_id = web_context.client.allowed_players_by_id
        players: list[Player] = []
        for player_id in player_ids:
            if player := allowed_players_by_id.get(player_id, None):
                players.append(player)
        player_comparators = await data_source.get_player_comparators(
            players, fields, diff_only=True
        )
        if player_comparators is None:
            Message.error(
                request,
                _(
                    'Connection to the data source [{data_source}] failed. '
                    'Consult the logs for more details.'
                ).format(data_source=data_source.name),
            )
        else:
            event.update_players(
                [
                    comparator.updated_player_from_match(fields)
                    for comparator in player_comparators
                ]
            )
            count: int = len(player_comparators)
            Message.success(
                request,
                ngettext(
                    '{count} player updated.', '{count} players updated.', count
                ).format(count=count)
                if count
                else _('No players updated.'),
            )
        web_context = PlayerAdminWebContext(request, reload_event=True)
        return self._render_players_tab(web_context)

    @get(
        path='/event-players-diff-modal/{event_uniq_id:str}/{data_source_id:str}',
        name='admin-event-players-diff-modal',
        guards=[TournamentActionGuard(AuthAction.UPDATE_PLAYERS)],
    )
    async def htmx_admin_event_players_diff_modal(
        self,
        request: HTMXRequest,
        data_source_id: str,
        tournament_id: int | None = None,
    ) -> Template:
        web_context = PlayerAdminWebContext(
            request,
            tournament_id=tournament_id,
            data_source_id=data_source_id,
        )
        data_source = web_context.get_admin_data_source()
        players: list[Player] = []
        if tournament := web_context.admin_tournament:
            for (
                tournament_player
            ) in tournament.tournament_players_by_name_with_unpaired:
                players.append(tournament_player)
        else:
            players = web_context.client.sorted_allowed_players
        fields = data_source.player_updater_fields
        player_comparators = await data_source.get_player_comparators(players, fields)
        if player_comparators is None:
            Message.error(
                request,
                _('Could not connect to data source [{data_source}].').format(
                    data_source=data_source.name
                ),
            )
            return self._render_players_tab(web_context)
        updated_field_ids = {
            field_id
            for comparator in player_comparators
            for field_id in comparator.diff_field_ids
        }
        template_context = web_context.template_context | {
            'modal': 'players_diff',
            'data_source': data_source,
            'fields': fields,
            'updated_field_ids': updated_field_ids,
            'player_comparators': player_comparators,
            'update_enabled': bool(updated_field_ids),
        }
        return self._admin_base_event_render(template_context)

    @classmethod
    def publish_new_checkin(
        cls, channels: ChannelsPlugin, event_uniq_id: str, player: Player
    ):
        channels.publish(
            {'event': f'new-checkins|{event_uniq_id}', 'data': ''},
            ['ws'],
        )
        channels.publish(
            {
                'event': f'new-checkins|{event_uniq_id}|{player.single_tournament.id}|{player.single_tournament.current_round}',
                'data': '',
            },
            ['ws'],
        )

    @get(
        path='/players/needs-refresh-message/{event_uniq_id:str}/{reason:str}',
        name='admin-players-needs-refresh-message',
    )
    async def htmx_admin_players_refresh_message(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        reason: str,
    ) -> Template:
        return HTMXTemplate(
            template_name='/admin/common/needs_refresh.html',
            context={
                'url': request.app.route_reverse(
                    'admin-event-players-tab', event_uniq_id=event_uniq_id
                ),
                'event_uniq_id': event_uniq_id,
                'reason': reason,
            },
        )

    @get(
        path=[
            '/search-player/{event_uniq_id:str}',
            '/search-player/{event_uniq_id:str}/{page:int}',
        ],
        name='admin-search-player',
    )
    async def htmx_admin_search_player(
        self,
        request: HTMXRequest,
        data_source_id: str,
        player_id: int | None,
        search: str,
        page: int = 0,
        results_template: str | None = None,
        result_js_template_hook_name: str | None = None,
        augment_arbiter_title: bool = False,
    ) -> Template:
        web_context = PlayerAdminWebContext(
            request, player_id, data_source_id=data_source_id
        )
        data_source = web_context.get_admin_data_source()
        players: list[Player] = []
        connection_error: str | None = None
        search = search.strip()
        if search:
            try:
                stored_players = await data_source.search_player(
                    search,
                    web_context.get_admin_event().federation,
                    page,
                    DataSource.SEARCH_LIMIT,
                )
                for stored_player in stored_players:
                    player_source_id = data_source.get_player_source_id(stored_player)
                    fetched_player: (
                        StoredPlayer | None
                    ) = await data_source.fetch_player(
                        player_source_id=player_source_id,
                        augment_arbiter_title=augment_arbiter_title,
                    )
                    if not fetched_player:
                        raise NotFoundException(
                            f'Player [{player_source_id}] unexpectedly '
                            f'not found in data source [{data_source_id}]'
                        )
                    fetched_player.id = 0
                    players.append(
                        Player(web_context.get_admin_event(), fetched_player)
                    )
            except SharlyChessException as e:
                connection_error = str(e)
            SessionPlayersActiveDataSource(request).set(data_source.id)
        result_js_templates: list[str] = (
            plugin_manager.hook_for_event(
                web_context.get_admin_event(), result_js_template_hook_name
            )()
            if result_js_template_hook_name
            else []
        )
        return HTMXTemplate(
            template_name=results_template or 'admin/players/search_results.html',
            context=web_context.template_context
            | {
                'search': search,
                'search_results': players,
                'result_js_templates': result_js_templates,
                'has_more_results': len(players) == DataSource.SEARCH_LIMIT,
                'page': page,
                'data_source': data_source,
                'connection_error': connection_error,
            },
        )

    @get(
        path='/download-event-players/{event_uniq_id:str}/{exporter_id:str}',
        name='admin-download-event-players',
    )
    async def htmx_admin_event_download_players(
        self,
        request: HTMXRequest,
        exporter_id: str,
    ) -> Response[str] | File:
        web_context = PlayerAdminWebContext(request)
        event = web_context.get_admin_event()
        search_results = self.get_search_results(web_context)
        players: list[Player] = [
            event.players_by_id[player_id]
            for player_id in search_results
            if player_id in event.players_by_id
        ]
        try:
            exporter = PlayerExporterManager().get_object(exporter_id)
        except KeyError:
            raise NotFoundException(f'Unknown exporter [{exporter_id}].')
        return exporter.download_players_file(players, event)
