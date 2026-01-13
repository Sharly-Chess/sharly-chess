import csv
from collections import defaultdict
from collections.abc import Callable
from datetime import date
from logging import Logger
import math
from tempfile import NamedTemporaryFile
from typing import Annotated, Any, Iterable

from litestar.exceptions import NotFoundException, ClientException

from common.i18n.utils import normalized_key
from pyexcel_ods3 import save_data
import xlsxwriter

from litestar import get, patch, delete, post, Response
from litestar.plugins.htmx import HTMXRequest, ClientRedirect
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
from data.columns import player_datasheet as ds_columns
from data.columns.player_datasheet import DatasheetColumn
from data.event import Event
from data.access_levels.actions import AuthAction
from data.access_levels.client import Client
from data.input_output.data_source import DataSource
from data.input_output.managers import DataSourceManager
from data.player import Player, Federation, Club, PlayerRating, TournamentPlayer
from data.player_categories import PlayerCategory
from data.print_documents.documents import (
    PlayerListPrintDocument,
    PlayerCheckinListPrintDocument,
)
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredPlayer
from utils import Utils
from utils.enum import (
    PlayerGender,
    TournamentRating,
    PlayerRatingType,
    PlayerTitle,
    Result,
)
from plugins.manager import plugin_manager
from plugins.utils import ExtraAdminColumn
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.guards import (
    EventGuard,
    RequestUtils,
    TournamentActionGuard,
    ActionGuard,
    SetByeGuard,
    PlayerTournamentActionGuard,
)
from web.messages import Message
from web.session import (
    SessionPlayersEvent,
    SessionPlayersSort,
    SessionPlayersFilterColumns,
    SessionPlayersFilterFederations,
    SessionPlayersFilterName,
    SessionPlayersFilterClubsSearch,
    SessionPlayersFilterGenders,
    SessionPlayersFilterCheckIns,
    SessionPlayersFilterTournaments,
    SessionPlayersFilterCategories,
    SessionPlayersFilterClubs,
    SessionPlayersSearchResultsId,
    SessionPlayersActiveDataSource,
    SessionPlayersAddOtherActive,
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

        print_tournament_ids = self.default_tournament_for_print_modal(
            tournament_id=None
        )
        if print_tournament_ids is None:
            tournaments = list(self.admin_event.tournaments_by_id.values())
        else:
            tournaments = [
                self.admin_event.tournaments_by_id[tournament_id]
                for tournament_id in print_tournament_ids
            ]
        check_in_open = all(tournament.check_in_open for tournament in tournaments)
        self.default_print_document = (
            PlayerCheckinListPrintDocument.static_id()
            if check_in_open
            else PlayerListPrintDocument.static_id()
        )

    def get_admin_tournament(self) -> Tournament:
        assert self.admin_tournament is not None
        return self.admin_tournament

    def get_admin_player(self) -> Player:
        assert self.admin_player is not None
        return self.admin_player

    def get_admin_data_source(self) -> DataSource:
        assert self.admin_data_source is not None
        return self.admin_data_source

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_player': self.admin_player,
            'admin_tournament': self.admin_tournament,
            'default_print_document': self.default_print_document,
        }


class PlayerAdminController(BaseEventAdminController):
    PAGE_SIZE = 25
    search_results_by_session: dict[int, list[int]] = {}

    guards = [
        EventGuard(),
        ActionGuard(AuthAction.VIEW_PLAYERS_TAB),
    ]

    @classmethod
    def _admin_validate_player_update_data(
        cls,
        action: str,
        web_context: PlayerAdminWebContext,
        data: dict[str, str],
    ) -> dict[str, str]:
        assert web_context.admin_event is not None
        errors: dict[str, str] = {}
        tournament: Tournament | None = None
        field = 'tournament_id'
        try:
            tournament_id = WebContext.form_data_to_int(data, field)
            if not tournament_id:
                raise ValueError('Tournament ID not supplied')
            tournament = web_context.admin_event.tournaments_by_id[tournament_id]
        except (ValueError, KeyError):
            errors[field] = _('Please choose the tournament.')
        player: Player | None = None
        if action in ['update', 'replace'] and tournament is not None:
            player = web_context.get_admin_player()
            if tournament.id != player.single_tournament_player.tournament.id:
                try:
                    cls._validate_player_tournament_move(
                        web_context.admin_event,
                        player,
                        player.single_tournament_player.tournament,
                        tournament,
                    )
                except ValueError as e:
                    errors[field] = str(e)

        last_name: str | None = WebContext.form_data_to_str(data, field := 'last_name')
        if not last_name:
            errors[field] = _('This field is required.')
        try:
            WebContext.form_data_to_date(data, field := 'date_of_birth')
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
            if value := WebContext.form_data_to_int(data, field := 'gender'):
                PlayerGender(value)
        except ValueError:
            # should never happen, not translated.
            errors[field] = f'Invalid gender value [{data[field]}].'
            data[field] = ''
        try:
            if value := WebContext.form_data_to_int(data, field := 'title'):
                PlayerTitle(value)
        except ValueError:
            # should never happen, not translated.
            errors[field] = f'Invalid title value [{data[field]}].'
            data[field] = ''
        federation = WebContext.form_data_to_str(data, field := 'federation', '')
        if federation not in SharlyChessConfig.federations:
            # should never happen, not translated.
            errors[field] = f'Invalid federation value [{data[field]}].'
            data[field] = ''
        try:
            fide_id = WebContext.form_data_to_int(data, field := 'fide_id', minimum=1)
            if (
                action == 'create'
                and tournament
                and fide_id
                and fide_id in tournament.tournament_players_by_fide_id
            ):
                errors[field] = _(
                    'The player with FIDE ID [{fide_id}] already plays tournament [{tournament}].'
                ).format(fide_id=fide_id, tournament=tournament.name)
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

        plugin_manager.hook_for_event(
            web_context.get_admin_event(), 'validate_player_form_fields'
        )(action=action, tournament=tournament, player=player, data=data, errors=errors)
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
            gender=WebContext.form_data_to_int(data, 'gender')
            or PlayerGender.NONE.value,
            mail=WebContext.form_data_to_str(data, 'mail'),
            phone=WebContext.form_data_to_str(data, 'phone'),
            comment=data.get('comment'),
            owed=WebContext.form_data_to_float(data, 'owed') or 0.0,
            paid=WebContext.form_data_to_float(data, 'paid') or 0.0,
            title=WebContext.form_data_to_int(data, 'title') or PlayerTitle.NONE.value,
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

    @staticmethod
    def _get_gender_options() -> dict[str, str]:
        return {
            WebContext.value_to_form_data(gender.value): gender.name
            for gender in PlayerGender
        }

    @classmethod
    def filtered_players(
        cls, request: HTMXRequest, players: Iterable[Player]
    ) -> list[Player]:
        web_context = PlayerAdminWebContext(request)
        event = web_context.get_admin_event()
        allowed_tournaments = web_context.client.allowed_tournaments_for_action(
            AuthAction.VIEW_PLAYERS_TAB
        )
        allowed_tournament_ids = [tournament.id for tournament in allowed_tournaments]
        allowed_players_by_id = web_context.client.allowed_players_by_id
        allowed_players = allowed_players_by_id.values()
        # The federations that will be shown on the federation select list
        players_federations = sorted({player.federation for player in allowed_players})
        # The federations that will be selected on the federation select list and used to filter the players
        filter_federations = [
            f
            for f in SessionPlayersFilterFederations(request).get()
            if f in players_federations
        ]
        # The clubs that will be shown on the club select list
        players_clubs = sorted(
            {player.club for player in allowed_players if player.club is not None}
        )
        # The clubs that will be selected on the club select list and used to filter the players
        filter_clubs = [
            c for c in SessionPlayersFilterClubs(request).get() if c in players_clubs
        ]
        # The genders that will be selected on the gender select list and used to filter the players
        filter_genders = SessionPlayersFilterGenders(request).get()
        # The check-in statuses that will be selected on the
        # check-in status select list and used to filter the players
        filter_check_ins = SessionPlayersFilterCheckIns(request).get()
        # The tournaments that will be selected on the tournament select list and used to filter the players
        filter_tournaments = set(
            SessionPlayersFilterTournaments(request).get()
        ).intersection(set(allowed_tournament_ids))

        # The categories that will be shown on the category select list
        players_categories = sorted(
            {player.single_tournament_player.category for player in allowed_players}
        )
        # The categories that will be selected on the category select list and used to filter the players
        filter_categories = SessionPlayersFilterCategories(request).get()
        # The name the players must match
        filter_name = SessionPlayersFilterName(request).get()
        # The origin (federation+league+club) the players must match
        filter_origin = SessionPlayersFilterClubsSearch(request).get()

        filters: list[Callable[[Player], bool]] = []
        if len(filter_genders) not in (0, 3):
            filters.append(lambda player: player.gender in filter_genders)
        if len(filter_categories) not in (0, len(players_categories)):
            filters.append(
                lambda player: player.single_tournament_player.category
                in filter_categories
            )
        if len(filter_check_ins) not in (0, 3):
            filters.append(
                lambda player: (
                    (
                        player.single_tournament_player.can_check_in_out
                        and player.check_in in filter_check_ins
                    )
                    or (
                        not player.single_tournament_player.can_check_in_out
                        and None in filter_check_ins
                    )
                )
            )
        if len(filter_tournaments) not in (0, len(allowed_tournaments)):
            filters.append(
                lambda player: player.single_tournament_player.tournament.id
                in filter_tournaments
            )
        if len(filter_federations) not in (0, len(players_federations)):
            filters.append(lambda player: player.federation in filter_federations)
        if len(filter_clubs) not in (0, len(players_clubs)):
            filters.append(lambda player: player.club in filter_clubs)
        if filter_name:
            filters.append(
                lambda player: cls._matches_string_search(
                    filter_name, f'{player.last_name} {player.first_name}'
                )
            )
        if filter_origin:
            filters.append(
                lambda player: cls._matches_string_search(
                    filter_origin, f'{player.federation} {player.club}'
                )
            )
        per_plugin_context = plugin_manager.hook_for_event(
            event, 'get_player_admin_template_context'
        )(web_context=web_context)
        plugin_context = {
            key: value
            for context in per_plugin_context
            for key, value in context.items()
        }
        for plugin_filters in plugin_manager.hook_for_event(event, 'player_filters')(
            web_context=web_context,
            template_context=web_context.template_context | plugin_context,
        ):
            filters += plugin_filters
        return [
            player
            for player in players
            if player.id in allowed_players_by_id
            and all(filter_(player) for filter_ in filters)
        ]

    @staticmethod
    def _matches_string_search(search: str, match: str):
        search_parts = set(search.split(' '))
        match_str = normalized_key(match)
        return all(search_part in match_str for search_part in search_parts)

    @staticmethod
    def sorted_player_ids(
        event: Event, players: list[Player], sort_type: str
    ) -> list[int]:
        def get_sort_key(player: Player) -> tuple:
            if sortkey := plugin_manager.hook_for_event(event, 'player_sort_key')(
                player=player, sort_type=sort_type
            ):
                return sortkey

            match sort_type:
                case 'rating_desc':
                    return (
                        -player.single_tournament_player.rating,
                        player.last_name,
                        player.first_name,
                    )
                case 'rating_asc':
                    return (
                        player.single_tournament_player.rating,
                        player.last_name,
                        player.first_name,
                    )
                case 'yob_desc':
                    return (
                        date.today()
                        - (
                            player.date_of_birth
                            or date(player.year_of_birth or date.today().year, 1, 1)
                        ),
                        player.last_name,
                        player.first_name,
                    )
                case 'yob_asc':
                    return (
                        (
                            player.date_of_birth
                            or date(player.year_of_birth or 1900, 12, 31)
                        )
                        - date.today(),
                        player.last_name,
                        player.first_name,
                    )
                case 'club':
                    return (
                        player.club,
                        player.last_name,
                        player.first_name,
                    )
                case 'tournament':
                    assert player.single_tournament_player.tournament is not None
                    return (
                        player.single_tournament_player.tournament.name,
                        -player.single_tournament_player.rating,
                        player.last_name,
                        player.first_name,
                    )
                case _:  # 'alpha' and default sort
                    return player.last_name, player.first_name

        return [player.id for player in sorted(players, key=get_sort_key)]

    @classmethod
    def set_players_search_results(cls, request: HTMXRequest) -> list[int]:
        web_context = PlayerAdminWebContext(request)
        event = web_context.get_admin_event()
        filtered_players = cls.filtered_players(request, event.players_by_id.values())
        sort_type = SessionPlayersSort(request).get()
        search_results = cls.sorted_player_ids(event, filtered_players, sort_type)
        results_session_id = SessionPlayersSearchResultsId(request).get()
        if not results_session_id:
            results_session_id = (
                max([0] + [id_ for id_ in cls.search_results_by_session]) + 1
            )
            SessionPlayersSearchResultsId(request).set(results_session_id)
        cls.search_results_by_session[results_session_id] = search_results
        SessionPlayersEvent(request).set(event.uniq_id)
        return search_results

    @classmethod
    def delete_from_search_results(cls, request: HTMXRequest, player_id: int):
        results_session_id = SessionPlayersSearchResultsId(request).get()
        if not results_session_id:
            return
        try:
            cls.search_results_by_session[results_session_id].remove(player_id)
        except ValueError:
            pass

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
    def _admin_event_players_render(
        cls,
        request: HTMXRequest,
        modal: str | None = None,
        action: str | None = None,
        player_id: int | None = None,
        old_player_id: int | None = None,
        deleted_player_id: int | None = None,
        search_stored_player: StoredPlayer | None = None,
        tournament_id: int | None = None,
        page: int | None = None,
        reload_event: bool = False,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
        warning_message: str | None = None,
    ) -> Template:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request, player_id, tournament_id, reload_event=reload_event
        )
        event = web_context.get_admin_event()
        session_event_uniq_id = SessionPlayersEvent(request).get()
        search_results_id = SessionPlayersSearchResultsId(request).get()

        if (
            search_results_id is None
            or session_event_uniq_id != event.uniq_id
            or search_results_id not in cls.search_results_by_session
        ):
            search_results = cls.set_players_search_results(request)
        else:
            search_results = cls.search_results_by_session[search_results_id]
        allowed_tournaments = web_context.client.allowed_tournaments_for_action(
            AuthAction.VIEW_PLAYERS_TAB
        )
        allowed_tournament_ids = [tournament.id for tournament in allowed_tournaments]
        allowed_players_by_id = web_context.client.allowed_players_by_id
        allowed_players = web_context.client.sorted_allowed_players
        players: dict[int, Player] = {}
        start_index = ((page or 1) - 1) * cls.PAGE_SIZE
        end_index = (page or 1) * cls.PAGE_SIZE
        pages = math.ceil(len(search_results) / cls.PAGE_SIZE)
        for index, player_id in enumerate(search_results[start_index:end_index]):
            if player := allowed_players_by_id.get(player_id, None):
                players[start_index + index + 1] = player

        admin_player: Player | None = web_context.admin_player

        # Allow plugin to provide extra columns
        per_plugin_columns: Iterable[Iterable[ExtraAdminColumn]] = (
            plugin_manager.hook_for_event(event, 'get_extra_player_columns')()
        )
        extra_columns: dict[str, list[ExtraAdminColumn]] = {}
        for plugin_columns in per_plugin_columns:
            for extra_column in plugin_columns:
                c = extra_columns.setdefault(extra_column.at, [])
                c.append(extra_column)

        # The federations that will be shown on the federation select list
        players_federations: list[Federation] = sorted(
            {player.federation for player in allowed_players}
        )
        # The clubs that will be shown on the club select list
        players_clubs: list[Club] = sorted(
            {player.club for player in allowed_players if player.club is not None}
        )
        # The genders that will be shown on the gender select list
        players_genders: list[PlayerGender] = sorted(
            {player.gender for player in allowed_players}
        )
        # The years or birth that will be shown on the year of birth select list
        players_yobs: list[int] = sorted(
            {player.year_of_birth for player in allowed_players}
        )
        # The check-in statuses that will be selected on the
        # check-in status select list and used to filter the players
        players_check_ins: list[bool | None] = [None, True, False]
        # The categories that will be shown on the category select list
        players_categories: list[PlayerCategory] = sorted(
            {player.single_tournament_player.category for player in allowed_players}
        )
        player_addable_tournaments = [
            tournament
            for tournament in event.player_addable_tournaments
            if tournament.id in allowed_tournament_ids
        ]

        template_context = web_context.template_context
        template_context |= {
            'admin_event_tab': 'admin-event-players-tab',
            'admin_players': players,
            'admin_filtered_player_count': len(search_results),
            'page': page or 1,
            'pages': pages,
            'nav_tab_title': _('Players ({num})').format(num=len(allowed_players)),
            'allowed_tournaments': allowed_tournaments,
            'allowed_players': allowed_players,
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
            'admin_players_sort': SessionPlayersSort(request).get(),
            'admin_players_federations': players_federations,
            'admin_players_clubs': players_clubs,
            'admin_players_yobs': players_yobs,
            'admin_players_categories': players_categories,
            'admin_players_genders': players_genders,
            'admin_players_check_ins': players_check_ins,
            'admin_players_filter_columns': SessionPlayersFilterColumns(request).get(),
            'admin_players_filter_federations': SessionPlayersFilterFederations(
                request
            ).get(),
            'admin_players_filter_clubs': SessionPlayersFilterClubs(request).get(),
            'admin_players_filter_clubs_search': SessionPlayersFilterClubsSearch(
                request
            ).get(),
            'admin_players_filter_genders': SessionPlayersFilterGenders(request).get(),
            'admin_players_filter_check_ins': SessionPlayersFilterCheckIns(
                request
            ).get(),
            'admin_players_filter_tournaments': SessionPlayersFilterTournaments(
                request
            ).get(),
            'admin_players_filter_categories': SessionPlayersFilterCategories(
                request
            ).get(),
            'admin_players_filter_name': SessionPlayersFilterName(request).get(),
            'admin_players_extra_columns': extra_columns,
            'data_sources': DataSourceManager().objects(),
            'player_addable_tournaments': player_addable_tournaments,
        }
        template_context |= Utils.concat_dicts(
            plugin_manager.hook_for_event(event, 'get_player_admin_template_context')(
                web_context=web_context
            )
        )

        match modal:
            case None:
                pass
            case 'player':
                if data is None:
                    first_name: str | None = None
                    last_name: str | None = None
                    date_of_birth: str | None = None
                    gender: int = PlayerGender.NONE.value
                    ratings: dict[TournamentRating, PlayerRating] = {
                        tr: PlayerRating(estimated=0) for tr in TournamentRating
                    }
                    title: int = PlayerTitle.NONE.value
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
                    if not stored_player and admin_player and action != 'replace':
                        stored_player = admin_player.stored_player
                    if stored_player:
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
                        mail = stored_player.mail
                        phone = stored_player.phone
                        comment = stored_player.comment
                        owed = stored_player.owed
                        paid = stored_player.paid
                        fixed = stored_player.fixed
                        stored_plugin_data = stored_player.plugin_data
                    if action == 'create':
                        if len(event.not_finished_tournaments_sorted_by_index) == 1:
                            tournament_id = (
                                event.not_finished_tournaments_sorted_by_index[0].id
                            )
                    else:
                        assert admin_player is not None
                        tournament_id = (
                            admin_player.single_tournament_player.tournament.id
                        )

                    rating_data: dict[str, Any] = {}
                    for tournament_rating in TournamentRating:
                        rating_ = ratings[tournament_rating]
                        key = tournament_rating.form_key
                        rating_data |= {
                            f'{key}_rating_fide': WebContext.value_to_form_data(
                                rating_.fide or None
                            ),
                            f'{key}_rating_national': WebContext.value_to_form_data(
                                rating_.national or None
                            ),
                            f'{key}_rating_estimated': WebContext.value_to_form_data(
                                rating_.estimated or None
                            ),
                        }

                    plugin_form_data: dict[str, str] = {}
                    for (
                        plugin_id,
                        plugin_data_class,
                    ) in Player.plugin_data_class_by_plugin_id().items():
                        plugin_form_data |= plugin_data_class.from_stored_value(
                            stored_plugin_data.get(plugin_id, {})
                        ).to_form_data(action=action)

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
                    )
                if errors is None:
                    errors = {}
                tournaments = player_addable_tournaments
                tournament_options: dict[str, str] = {}
                if action == 'create' and len(tournaments) > 1:
                    # force the choice of the tournament on player creation if several tournaments
                    tournament_options |= {'': '-'}
                elif action in ['update', 'replace']:
                    assert admin_player is not None
                    if (
                        admin_player.single_tournament_player.tournament
                        not in tournaments
                    ):
                        tournaments.insert(
                            0, admin_player.single_tournament_player.tournament
                        )
                tournament_options |= web_context.get_tournament_options(tournaments)
                plugin_templates_by_section: dict[str, list[str]] = defaultdict(list)
                plugin_manager.hook_for_event(
                    event, 'insert_player_form_fields_template'
                )(templates_by_section=plugin_templates_by_section)

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
                    'selected_data_source': SessionPlayersActiveDataSource(
                        request
                    ).get(),
                    'data_source_options': DataSourceManager().options(),
                    'plugin_templates_by_section': plugin_templates_by_section,
                    'previous_player': (
                        allowed_players_by_id.get(old_player_id, None)
                        if action == 'create' and old_player_id
                        else None
                    ),
                    'warning_message': warning_message,
                    'add_other_active': SessionPlayersAddOtherActive(request).get(),
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
                template_context |= Utils.concat_dicts(
                    plugin_manager.hook_for_event(
                        event, 'get_player_form_template_context'
                    )(web_context=web_context)
                )

            case 'player-delete':
                assert admin_player is not None
                template_context |= {
                    'modal': modal,
                }
            case 'record':
                assert admin_player is not None
                tournament = admin_player.single_tournament_player.tournament
                data = {
                    f'round_{round_}_result': WebContext.value_to_form_data(
                        admin_player.single_tournament_player.pairings[
                            round_
                        ].result.value
                    )
                    for round_ in range(
                        max(1, tournament.current_round),
                        tournament.rounds + 1,
                    )
                }
                template_context |= {
                    'get_bye_options': cls._get_bye_options,
                    'modal': modal,
                    'data': data,
                }
            case 'close_check_in':
                template_context |= {
                    'modal': modal,
                }
            case _:
                raise ValueError(f'modal=[{modal}]')

        if admin_player is not None and modal is None:
            player_index: int | None
            try:
                player_index = search_results.index(admin_player.id) + 1
            except ValueError:
                player_index = None
            template_context |= {
                'index': player_index,
                'old_player_id': old_player_id,
            }

            return HTMXTemplate(
                template_name='/admin/players/table_header_and_player.html',
                context=template_context,
                re_target='#modal-wrapper',
                trigger_event='renumber_players_and_close_modal'
                if modal is None
                else 'close_modal',
                after='settle',
            )

        if deleted_player_id is not None:
            template_context |= {
                'deleted_player_id': deleted_player_id,
            }
            return HTMXTemplate(
                template_name='/admin/players/table_header_and_player.html',
                context=template_context,
                re_target='#modal-wrapper',
                trigger_event='renumber_players_and_close_modal',
                after='settle',
            )

        if page:
            return HTMXTemplate(
                template_name='/admin/players/table_players_page.html',
                context=template_context,
            )

        return cls._admin_base_event_render(template_context)

    @get(
        path='/event/{event_uniq_id:str}/players',
        name='admin-event-players-tab',
    )
    async def htmx_admin_event_players_tab(
        self,
        request: HTMXRequest,
        admin_players_sort: str | None = None,
        admin_players_filter_columns: list[str] | None = None,
        admin_players_filter_federations: list[str] | None = None,
        admin_players_filter_clubs: list[str] | None = None,
        admin_players_filter_clubs_search: str | None = None,
        admin_players_filter_genders: list[int] | None = None,
        admin_players_filter_check_ins: list[int] | None = None,
        admin_players_filter_tournaments: list[int] | None = None,
        admin_players_filter_categories: list[str] | None = None,
        admin_players_filter_name: str | None = None,
        admin_players_clear_filters: int | None = None,
    ) -> Template:
        event = RequestUtils.get_optional_event(request)
        if admin_players_sort is not None:
            SessionPlayersSort(request).set(admin_players_sort)
        elif admin_players_filter_name is not None:
            SessionPlayersFilterName(request).set(
                normalized_key(admin_players_filter_name)
            )
        elif admin_players_filter_columns is not None:
            SessionPlayersFilterColumns(request).set(
                [
                    column
                    for column in admin_players_filter_columns
                    if column  # '' must be ignored
                ]
            )
        elif admin_players_filter_federations is not None:
            SessionPlayersFilterFederations(request).set(
                [
                    Federation.from_query_param(query_param)
                    for query_param in admin_players_filter_federations
                    if query_param != '*'
                ]
            )
        elif admin_players_filter_clubs is not None:
            SessionPlayersFilterClubs(request).set(
                [
                    Club.from_query_param(query_param)
                    for query_param in admin_players_filter_clubs
                    if query_param != '*'
                ]
            )
        elif admin_players_filter_clubs_search is not None:
            SessionPlayersFilterClubsSearch(request).set(
                normalized_key(admin_players_filter_clubs_search)
            )
        elif admin_players_filter_genders is not None:
            SessionPlayersFilterGenders(request).set(
                [
                    PlayerGender(query_param)
                    for query_param in admin_players_filter_genders
                    if query_param >= 0  # -1 must be ignored
                ]
            )
        elif admin_players_filter_check_ins is not None:
            SessionPlayersFilterCheckIns(request).set(
                [
                    {
                        0: None,
                        1: False,
                        2: True,
                    }.get(query_param, None)
                    for query_param in admin_players_filter_check_ins
                    if query_param >= 0  # -1 must be ignored
                ]
            )
        elif admin_players_filter_tournaments is not None:
            SessionPlayersFilterTournaments(request).set(
                [
                    query_param
                    for query_param in admin_players_filter_tournaments
                    if query_param > 0  # 0 must be ignored
                ]
            )
        elif admin_players_filter_categories is not None:
            SessionPlayersFilterCategories(request).set(
                [
                    PlayerCategory.from_id(query_param)
                    for query_param in admin_players_filter_categories
                    if query_param  # '' must be ignored
                ]
            )
        elif admin_players_clear_filters:
            SessionPlayersFilterName(request).unset()
            SessionPlayersFilterFederations(request).unset()
            SessionPlayersFilterClubs(request).unset()
            SessionPlayersFilterClubsSearch(request).unset()
            SessionPlayersFilterGenders(request).unset()
            SessionPlayersFilterCheckIns(request).unset()
            SessionPlayersFilterTournaments(request).unset()
            SessionPlayersFilterCategories(request).unset()
            plugin_manager.hook_for_event(event, 'clear_player_filters')(
                request=request
            )
        self.set_players_search_results(request)
        return self._admin_event_players_render(request)

    @get(
        path='/event/{event_uniq_id:str}/players/{page:int}',
        name='admin-event-players-page',
    )
    async def htmx_admin_event_players_page(
        self, request: HTMXRequest, page: int
    ) -> Template:
        return self._admin_event_players_render(request, page=page)

    @get(
        path='/player-row/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-row',
    )
    async def htmx_admin_player_row(
        self, request: HTMXRequest, player_id: int
    ) -> Template:
        return self._admin_event_players_render(request, player_id=player_id)

    @get(
        path='/player-modal/create/{event_uniq_id:str}',
        name='admin-player-create-modal',
    )
    async def htmx_admin_player_create_modal(self, request: HTMXRequest) -> Template:
        return self._admin_event_players_render(
            request,
            modal='player',
            action='create',
        )

    @get(
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
        data_source_id: str,
        player_source_id: str,
        player_id: int | None,
        tournament_id: str | None,
    ) -> Template:
        web_context = PlayerAdminWebContext(
            request, player_id, data_source_id=data_source_id
        )
        data_source = web_context.get_admin_data_source()
        errors: dict[str, str] = {}
        stored_player: StoredPlayer | None = None
        if not data_source.is_available:
            raise ClientException(f'Data source [{data_source_id}] is not available.')
        try:
            stored_player = await data_source.fetch_player(player_source_id)
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
        return self._admin_event_players_render(
            request,
            player_id=player_id,
            modal='player',
            action='replace' if player_id else 'create',
            search_stored_player=stored_player,
            tournament_id=int(tournament_id) if tournament_id else None,
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
        return self._admin_event_players_render(
            request,
            modal='player',
            action=action,
            player_id=player_id,
        )

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
        return self._admin_event_players_render(
            request,
            modal='player-delete',
            action='delete',
            player_id=player_id,
        )

    @get(
        path='/record-modal/{event_uniq_id:str}/{player_id:int}',
        name='admin-record-modal',
        guards=[PlayerTournamentActionGuard(AuthAction.UPDATE_PLAYERS_HISTORY)],
    )
    async def htmx_admin_record_modal(
        self, request: HTMXRequest, player_id: int
    ) -> Template:
        return self._admin_event_players_render(
            request,
            modal='record',
            player_id=player_id,
        )

    def _admin_player_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        action: str,
        player_id: int | None,
    ) -> Template:
        web_context = PlayerAdminWebContext(request, player_id=player_id)
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        add_other = 'add_other' in data
        if action == 'create':
            SessionPlayersAddOtherActive(request).set(add_other)
        errors = self._admin_validate_player_update_data(action, web_context, data)
        if errors:
            return self._admin_event_players_render(
                request,
                modal='player',
                action=action,
                player_id=player_id,
                data=data,
                errors=errors,
            )
        stored_player = self._stored_player_from_data(data)
        event = web_context.get_admin_event()
        tournament_id = WebContext.form_data_to_int(data, 'tournament_id') or 0
        tournament = event.tournaments_by_id[tournament_id]
        new_player_id: int | None = None
        match action:
            case 'update' | 'replace':
                player = web_context.get_admin_player()
                event.update_player(player, stored_player)
                previous_tournament = player.single_tournament_player.tournament
                if tournament.id != previous_tournament.id:
                    event.move_player_to_tournament(player, tournament)
                if not self.filtered_players(request, [player]):
                    self.delete_from_search_results(request, player.id)
            case 'create':
                if tournament.finished:
                    Message.error(
                        request,
                        _(
                            'Tournament [{tournament}] is finished, you can not add players any longer.'
                        ).format(tournament=tournament.name),
                    )
                    return self._admin_event_players_render(
                        request,
                        action=action,
                        data=data,
                        reload_event=True,
                    )
                player_id = event.add_player(stored_player, [tournament])
                self.set_players_search_results(request)
                player = tournament.tournament_players_by_id[player_id]
                warning_message: str | None = None
                if not tournament.player_matches_criteria(
                    player.single_tournament_player
                ):
                    warning_message = _(
                        'Player [{player}] has been created, but does not match tournament criteria: {names}'
                    ).format(
                        player=player.full_name,
                        names=player.single_tournament_player.tournament.failing_criteria_message(
                            player.single_tournament_player
                        ),
                    )
                if add_other:
                    return self._admin_event_players_render(
                        request,
                        modal='player',
                        action='create',
                        old_player_id=player_id,
                        warning_message=warning_message,
                        tournament_id=tournament.id,
                        reload_event=True,
                    )
                if warning_message:
                    Message.warning(
                        request,
                        warning_message,
                    )
                else:
                    Message.success(
                        request,
                        _('Player [{player}] has been created.').format(
                            player=player.full_name
                        ),
                    )
                return self._admin_event_players_render(request, reload_event=True)
            case _:
                raise ValueError(f'action=[{action}]')
        return self._admin_event_players_render(
            request,
            player_id=(new_player_id or player_id),
            old_player_id=player_id if new_player_id is not None else None,
            reload_event=True,
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

        return self._admin_event_players_render(
            web_context.request,
            modal='record',
            player_id=player.id,
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
        web_context = PlayerAdminWebContext(
            request,
            tournament_id=tournament_id,
            player_id=player_id,
        )
        return self._set_player_participation(
            web_context,
            Result.ZERO_POINT_BYE,
        )

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
        web_context = PlayerAdminWebContext(
            request,
            tournament_id=tournament_id,
            player_id=player_id,
        )

        return self._set_player_participation(
            web_context,
            Result.NO_RESULT,
        )

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
        src_tournament = admin_player.single_tournament_player.tournament
        event = web_context.get_admin_event()
        try:
            self._validate_player_tournament_move(
                event, admin_player, src_tournament, dst_tournament
            )
            event.move_player_to_tournament(admin_player, dst_tournament)
            if not self.filtered_players(request, [admin_player]):
                self.delete_from_search_results(request, admin_player.id)
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
        return self._admin_event_players_render(
            request,
            old_player_id=player_id,
            player_id=admin_player.id,
            reload_event=True,
        )

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
        return self._admin_player_update(
            request,
            action='create',
            player_id=None,
            data=data,
        )

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
        return self._admin_player_update(
            request,
            action='update',
            player_id=player_id,
            data=data,
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
        return self._admin_player_update(
            request,
            action='replace',
            player_id=player_id,
            data=data,
        )

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
        player.single_tournament_player.tournament.set_player_byes(
            player.single_tournament_player, {round: Result(result)}
        )
        return self._admin_event_players_render(
            request, player_id=player_id, modal='record', reload_event=True
        )

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
        tournament = player.single_tournament_player.tournament
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
            self.delete_from_search_results(request, player.id)
            deleted_player_id = player.id
        return self._admin_event_players_render(
            request,
            deleted_player_id=deleted_player_id,
            reload_event=True,
        )

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
        return self._admin_event_players_render(request, reload_event=True)

    @get(
        path='/tournament-close-check-in-modal/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-close-check-in-modal',
    )
    async def htmx_tournament_close_check_in_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        return self._admin_event_players_render(
            request,
            modal='close_check_in',
            tournament_id=tournament_id,
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

    def _admin_player_check_in_out(
        self,
        request: HTMXRequest,
        player_id: int,
        check_in: bool,
    ) -> Template:
        web_context = PlayerAdminWebContext(request, player_id)

        if web_context.admin_player is None:
            raise RuntimeError('admin_player not defined')
        admin_player: Player = web_context.admin_player
        if admin_player.single_tournament_player.tournament is None:
            raise RuntimeError('admin_player.tournament not defined')
        admin_player.single_tournament_player.tournament.check_in_player(
            admin_player, check_in
        )
        if not self.filtered_players(request, [admin_player]):
            self.delete_from_search_results(request, admin_player.id)
        return self._admin_event_players_render(
            request, player_id=player_id, reload_event=True
        )

    @patch(
        path='/player-check-in/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-check-in',
        guard=[PlayerTournamentActionGuard(AuthAction.CHECK_IN_PLAYERS)],
    )
    async def htmx_admin_player_check_in(
        self, request: HTMXRequest, player_id: int
    ) -> Template:
        return self._admin_player_check_in_out(
            request=request,
            player_id=player_id,
            check_in=True,
        )

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
        return self._admin_player_check_in_out(request, player_id, check_in=False)

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
        self.set_players_search_results(request)
        return self._admin_event_players_render(request, reload_event=True)

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
            return self._admin_event_players_render(request, reload_event=True)
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
        if player.single_tournament_player.tournament is not None:
            channels.publish(
                {
                    'event': f'new-checkins|{event_uniq_id}|{player.single_tournament_player.tournament.id}|{player.single_tournament_player.tournament.current_round}',
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
                players = []
                for stored_player in stored_players:
                    stored_player.id = 0
                    players.append(Player(web_context.get_admin_event(), stored_player))
            except SharlyChessException as e:
                connection_error = str(e)
            SessionPlayersActiveDataSource(request).set(data_source.id)
        return HTMXTemplate(
            template_name=results_template or 'admin/players/search_results.html',
            context=web_context.template_context
            | {
                'search': search,
                'search_results': players,
                'has_more_results': len(players) == DataSource.SEARCH_LIMIT,
                'page': page,
                'data_source': data_source,
                'connection_error': connection_error,
            },
        )

    @staticmethod
    def download_players_as_vcf(
        event: Event,
        players: list[Player],
    ) -> Response[str]:
        """Returns a file with all the vCards of the players."""
        data: str = ''
        for player in players:
            if not (player.mail or player.phone):
                continue
            data += 'BEGIN:VCARD\nVERSION:3.0\n'
            if player.first_name:
                data += (
                    f'N:{player.last_name.title()};{player.first_name}\n'
                    f'FN:{player.first_name} {player.last_name.title()}\n'
                )
            else:
                data += f'N:{player.last_name.title()}\nFN:{player.last_name.title()}\n'
            data += (
                f'ORG:{player.club}\n'
                f'item1.TEL:{player.phone}\n'
                f'item1.X-ABLabel:{_("Personal")}\n'
                f'item2.EMAIL;type=INTERNET:{player.mail}\n'
                f'item2.X-ABLabel:{_("Personal")}\n'
                f'CATEGORIES:{_("Chess")}\n'
                'END:VCARD\n\n'
            )
        return Response(
            content=data,
            media_type='text/x-vcard',
            headers={
                'Content-Disposition': f'attachment;{event.uniq_id}.vcf',
            },
        )

    @classmethod
    def get_players_datasheet_column(cls, event: Event) -> list[DatasheetColumn]:
        """Returns the names of the columns used in the datasheets that can be downloaded."""

        datasheet_columns: list[DatasheetColumn] = [
            ds_columns.LastNameColumn(),
            ds_columns.FirstNameColumn(),
            ds_columns.YearOfBirthColumn(),
            ds_columns.DateOfBirthColumn(),
            ds_columns.MailColumn(),
            ds_columns.PhoneColumn(),
            ds_columns.GenderColumn(),
            ds_columns.FideIDColumn(),
            ds_columns.TournamentColumn(),
            ds_columns.FederationColumn(),
            ds_columns.ClubColumn(),
            ds_columns.OwedColumn(),
            ds_columns.PaidColumn(),
            ds_columns.CommentColumn(),
        ]
        for tournament_type in TournamentRating:
            for rating_type in PlayerRatingType:
                datasheet_columns.append(
                    ds_columns.RatingColumn(tournament_type, rating_type)
                )
        plugin_manager.hook_for_event(event, 'insert_player_datasheet_columns')(
            datasheet_columns=datasheet_columns
        )
        return datasheet_columns

    @classmethod
    def get_players_datasheet_header_and_data(
        cls, event: Event, players: list[Player]
    ) -> tuple[list[str], list[list[Any]]]:
        columns = cls.get_players_datasheet_column(event)
        header = [column.header_content for column in columns]
        data = [
            [column.get_cell_content(player) for column in columns]
            for player in players
        ]
        return header, data

    @classmethod
    def download_players_as_xlsx(
        cls,
        event: Event,
        players: list[Player],
    ) -> File:
        """Returns a file with all the information of the players in an XLSX format."""
        temp_file = NamedTemporaryFile(delete=False, mode='wb', suffix='.xlsx')
        workbook = xlsxwriter.Workbook(temp_file)
        worksheet = workbook.add_worksheet()
        header, data = cls.get_players_datasheet_header_and_data(event, players)
        worksheet.add_table(
            0,
            0,
            len(data),
            len(header) - 1,
            options={
                'columns': [{'header': header} for header in header],
                'data': data,
            },
        )
        worksheet.autofit()
        workbook.close()
        return File(path=temp_file.name, filename=f'{event.uniq_id}.xlsx')

    @classmethod
    def download_players_as_csv(
        cls,
        event: Event,
        players: list[Player],
    ) -> File:
        """Returns a file with all the information of the players in a CSV format (comma-separated)."""
        temp_file = NamedTemporaryFile(
            delete=False, mode='w', suffix='.csv', newline=''
        )
        writer = csv.writer(temp_file)
        header, data = cls.get_players_datasheet_header_and_data(event, players)
        writer.writerow(header)
        writer.writerows(data)
        return File(path=temp_file.name, filename=f'{event.uniq_id}.csv')

    @classmethod
    def download_players_as_ods(
        cls,
        event: Event,
        players: list[Player],
    ) -> File:
        """Returns a file with all the information of the players in an ODS format."""
        temp_file = NamedTemporaryFile(delete=False, mode='w+b', suffix='.ods')
        header, data = cls.get_players_datasheet_header_and_data(event, players)
        save_data(temp_file, [header] + data)
        return File(path=temp_file.name, filename=f'{event.uniq_id}.ods')

    @get(
        path='/download-event-players/{event_uniq_id:str}',
        name='admin-download-event-players',
    )
    async def htmx_admin_event_download_players(
        self,
        request: HTMXRequest,
        download_format: str | None = None,
        player_ids: list[int] | None = None,
    ) -> ClientRedirect | Response[str] | File:
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        players: list[Player] = [
            event.players_by_id[player_id]
            for player_id in player_ids or []
            if player_id
        ]
        if not players:
            players = event.players_sorted_by_name
        match download_format:
            case 'vcf':
                return self.download_players_as_vcf(event, players)
            case 'csv':
                return self.download_players_as_csv(event, players)
            case 'xlsx':
                return self.download_players_as_xlsx(event, players)
            case 'ods':
                return self.download_players_as_ods(event, players)
            case _:
                raise ValueError(f'download_format={download_format}')
