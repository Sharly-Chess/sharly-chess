from collections import defaultdict
from collections.abc import Callable
from datetime import date
from logging import Logger
import math
from typing import Annotated, Any, Iterable

from litestar import get, patch, delete, post
from litestar.plugins.htmx import HTMXRequest, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, Redirect
from litestar.status_codes import HTTP_200_OK
from litestar_htmx import HTMXTemplate

from common import unicode_normalize
from common.i18n import _, ngettext
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.event import Event
from data.input_output import PlayerUpdater, PlayerUpdaterManager
from data.input_output.player_updaters import PlayerComparator
from data.pairing import Pairing
from data.player import Player, Federation, Club, PlayerRating
from data.tournament import Tournament
from utils.enum import (
    PlayerCategory,
    PlayerGender,
    TournamentRating,
    PlayerRatingType,
    PlayerTitle,
    Result,
)
from database.sqlite.fide.fide_database import FideDatabase
from plugins.ffe.utils import PlayerFFELicence
from plugins.manager import plugin_manager
from plugins.utils import ExtraAdminColumn
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.messages import Message
from web.session import SessionHandler

logger: Logger = get_logger()


class PlayerAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        player_id: int | None = None,
        player_fide_id: int | None = None,
        player_from_plugin: Player | None = None,
        tournament_id: int | None = None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ]
        | None = None,
    ):
        super().__init__(request, event_uniq_id=event_uniq_id, data=data)
        if self.admin_event is None:
            raise RuntimeError('admin_event not defined')
        self.admin_player: Player | None = None
        self.admin_tournament: Tournament | None = None
        if self.error:
            return
        if player_id:
            try:
                self.admin_player = self.admin_event.players_by_id[player_id]
            except KeyError:
                self._redirect_error(f'Player [{player_id}] not found.')
                return
        elif player_fide_id:
            # player_fide_id is set when is a player is to be imported from the FIDE database
            if (fide_database := FideDatabase()).exists():
                with fide_database:
                    self.admin_player = fide_database.get_player_by_fide_id(
                        player_fide_id
                    )
            plugin_manager.hook.augment_player_after_search(player=self.admin_player)
        elif player_from_plugin:
            # A player has been returned via a plugin search
            self.admin_player = player_from_plugin

        if tournament_id:
            try:
                self.admin_tournament = self.admin_event.tournaments_by_id[
                    tournament_id
                ]
            except KeyError:
                self._redirect_error(f'Tournament [{tournament_id}] not found.')
                return

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_player': self.admin_player,
            'admin_tournament': self.admin_tournament,
        }


class PlayerAdminController(BaseEventAdminController):
    PAGE_SIZE = 50

    @classmethod
    def _admin_validate_player_update_data(
        cls,
        action: str,
        web_context: PlayerAdminWebContext,
        data: dict[str, str] | None = None,
    ) -> Player:
        assert web_context.admin_event is not None
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        field = ''
        if action in [
            'delete',
        ]:
            assert web_context.admin_player is not None
            return web_context.admin_player
        tournament: Tournament | None = None
        try:
            tournament_id = WebContext.form_data_to_int(data, field := 'tournament_id')
            if not tournament_id:
                raise ValueError('Tournament ID not supplied')
            tournament = web_context.admin_event.tournaments_by_id[tournament_id]
        except (ValueError, KeyError):
            errors[field] = _('Please choose the tournament.')
        if action == 'update' and tournament is not None:
            player = web_context.admin_player
            assert player is not None
            assert player.tournament is not None
            if tournament.id != player.tournament.id:
                try:
                    cls._validate_player_tournament_move(player, tournament)
                except ValueError as e:
                    errors[field] = str(e)

        last_name: str | None = WebContext.form_data_to_str(data, field := 'last_name')
        if not last_name:
            errors[field] = _('Please enter the last name.')
        else:
            last_name = last_name.upper()
        first_name: str | None = WebContext.form_data_to_str(data, 'first_name')
        if first_name:
            first_name = first_name.title() if first_name else ''
        date_of_birth: date | None = WebContext.form_data_to_date(
            data, field := 'date_of_birth'
        )
        if not date_of_birth:
            errors[field] = _('Please enter the date of birth.')
        gender: PlayerGender | None = PlayerGender.NONE
        try:
            if value := WebContext.form_data_to_int(data, field := 'gender'):
                gender = PlayerGender(value)
        except ValueError:
            # should never happen, not translated.
            errors[field] = f'Invalid gender value [{data[field]}].'
            data[field] = ''
        ratings: dict[TournamentRating, PlayerRating] = {
            tr: PlayerRating(
                value=WebContext.form_data_to_int(data, f'rating_{tr.value}') or 0,
                type=PlayerRatingType(
                    WebContext.form_data_to_int(data, f'rating_type_{tr.value}')
                    or PlayerRatingType.ESTIMATED.value
                ),
            )
            for tr in TournamentRating
        }
        for tr, rating in ratings.items():
            if rating.type != PlayerRatingType.ESTIMATED and not rating.value:
                errors[f'rating_type_{tr.value}'] = _(
                    'Only estimated ratings are optional.'
                )
        title: PlayerTitle | None = PlayerTitle.NONE
        try:
            if value := WebContext.form_data_to_int(data, field := 'title'):
                title = PlayerTitle(value)
        except ValueError:
            # should never happen, not translated.
            errors[field] = f'Invalid title value [{data[field]}].'
            data[field] = ''
        federation_name: str | None = WebContext.form_data_to_str(
            data, field := 'federation', SharlyChessConfig().default_federation
        )
        federation: Federation | None = None
        if federation_name not in SharlyChessConfig.federations:
            # should never happen, not translated.
            errors[field] = f'Invalid federation value [{data[field]}].'
            data[field] = ''
        else:
            federation = Federation(federation_name)
        club_name: str | None = WebContext.form_data_to_str(data, field := 'club')
        club: Club | None = Club(club_name) if club_name else None
        fide_id: int | None = None
        try:
            fide_id = WebContext.form_data_to_int(data, field := 'fide_id', minimum=1)
            if (
                action == 'create'
                and tournament
                and fide_id
                and fide_id in tournament.players_by_fide_id
            ):
                errors[field] = _(
                    'The player with FIDE ID [{fide_id}] already plays tournament [{tournament_uniq_id}].'
                ).format(fide_id=fide_id, tournament_uniq_id=tournament.uniq_id)
        except ValueError:
            errors[field] = _('Invalid FIDE ID [{fide_id}].').format(
                fide_id=data[field]
            )
        mail: str | None = None
        try:
            mail = WebContext.form_data_to_mail(data, field := 'mail')
        except ValueError:
            errors[field] = _('Invalid mail [{mail}].').format(mail=data[field])
        phone: str | None = None
        try:
            phone = WebContext.form_data_to_phone(data, field := 'phone')
        except ValueError:
            errors[field] = _('Invalid phone number [{phone}].').format(
                phone=data[field]
            )
        owed: float | None = 0.0
        try:
            owed = WebContext.form_data_to_float(data, field := 'owed')
        except ValueError:
            errors[field] = _('Invalid amount [{amount}].').format(amount=data[field])
        paid: float | None = 0.0
        try:
            paid = WebContext.form_data_to_float(data, field := 'paid')
        except ValueError:
            errors[field] = _('Invalid amount [{amount}].').format(amount=data[field])
        comment: str | None = data.get('comment')
        fixed: int | None = None
        try:
            fixed = WebContext.form_data_to_int(data, field := 'fixed', minimum=1)
        except ValueError:
            errors[field] = _('Invalid fixed board number [{fixed_board}].').format(
                fixed_board=data[field]
            )

        # Have plugins validate their fields and return private plugin data
        per_plugin_player_data = plugin_manager.hook.get_validated_player_form_fields(
            action=action, tournament=tournament, data=data, errors=errors
        )
        plugin_data = {
            key: value for data in per_plugin_player_data for key, value in data.items()
        }

        assert federation is not None
        assert gender is not None
        assert title is not None

        return Player(
            id=web_context.admin_player.id
            if action != 'create' and web_context.admin_player
            else 0,
            first_name=first_name or '',
            last_name=last_name or '',
            date_of_birth=date_of_birth,
            gender=gender,
            mail=mail,
            phone=phone,
            comment=comment,
            owed=owed,
            paid=paid,
            title=title,
            ratings=ratings,
            fide_id=fide_id,
            federation=federation,
            club=club,
            fixed=fixed,
            check_in=False,  # not taken into account when updating/creating/deleting the player
            pairings={},  # Pairings are read from Papi but not used
            tournament=tournament,
            errors=errors,
            plugin_data=plugin_data,
        )

    @staticmethod
    def _get_gender_options() -> dict[str, str]:
        return {
            WebContext.value_to_form_data(gender.value): gender.name
            for gender in PlayerGender
        }

    @classmethod
    def set_players_search_results(
        cls, request: HTMXRequest, event_uniq_id: str
    ) -> list[int]:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
        )
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context
        )

        admin_event = web_context.admin_event
        assert admin_event is not None

        # Allow plugin to provide extra columns
        per_plugin_columns: Iterable[Iterable[ExtraAdminColumn]] = (
            plugin_manager.hook.get_extra_player_columns()
        )
        extra_columns: dict[str, list[ExtraAdminColumn]] = {}
        for plugin_columns in per_plugin_columns:
            for extra_column in plugin_columns:
                c = extra_columns.setdefault(extra_column.at, [])
                c.append(extra_column)

        # The federations that will be shown on the federation select list
        players_federations: list[Federation] = sorted(
            {player.federation for player in admin_event.players_by_id.values()}
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
                for player in admin_event.players_by_id.values()
                if player.club is not None
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
        # The genders that will be selected on the gender select list and used to filter the players
        filter_genders: list[PlayerGender] = (
            SessionHandler.get_session_admin_players_filter_genders(web_context.request)
        )
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
        # The origin (federation+league+club) the players must match
        filter_origin: str = (
            SessionHandler.get_session_admin_players_filter_clubs_search(
                web_context.request
            )
        )
        per_plugin_context = plugin_manager.hook.get_player_admin_template_context(
            web_context=web_context
        )
        plugin_context = {
            key: value
            for context in per_plugin_context
            for key, value in context.items()
        }

        template_context |= plugin_context

        sort_type = SessionHandler.get_session_admin_players_sort(web_context.request)

        def get_sort_key(player: Player) -> tuple:
            match sort_type:
                case 'alpha':
                    return player.last_name, player.first_name
                case 'rating_desc':
                    return -player.rating, player.last_name, player.first_name
                case 'rating_asc':
                    return player.rating, player.last_name, player.first_name
                case 'yob_desc':
                    return -player.year_of_birth, player.last_name, player.first_name
                case 'yob_asc':
                    return player.year_of_birth, player.last_name, player.first_name
                case 'category_desc':
                    return -player.category, player.last_name, player.first_name
                case 'category_asc':
                    return player.category, player.last_name, player.first_name
                case 'club':
                    return plugin_manager.hook.player_club_sort_key(player=player) or (
                        player.club,
                        player.last_name,
                        player.first_name,
                    )
                case 'tournament':
                    assert web_context.admin_event is not None
                    return (
                        web_context.admin_event.tournaments_by_id[
                            player.tournament_id
                        ].uniq_id,
                        -player.rating,
                        player.last_name,
                        player.first_name,
                    )
                case _:
                    raise ValueError(f'sort={sort_type}')

        # 0 real players only
        # 1 all or no genders selected, or player matches
        # 2 all or no licences selected, or player matches
        # 3 all or no check_ins selected, or player matches
        # 4 less than two tournaments, all or no tournaments selected, or player matches
        # 5 less than two federations, all or no federations selected, or player matches
        # 6 less than two clubs, all or no clubs selected, or player matches

        filters: list[Callable[[Player], bool]] = []
        if len(filter_genders) not in (0, 3):
            filters.append(lambda player: player.gender in filter_genders)
        if len(filter_categories) not in (0, len(players_categories)):
            filters.append(lambda player: player.category in filter_categories)
        if len(filter_check_ins) not in (0, 3):
            filters.append(
                lambda player: (
                    (player.can_check_in_out and player.check_in in filter_check_ins)
                    or (not player.can_check_in_out and None in filter_check_ins)
                )
            )
        if len(filter_tournaments) not in (0, len(admin_event.tournaments_by_id)):
            filters.append(lambda player: player.tournament_id in filter_tournaments)
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
        for plugin_filters in plugin_manager.hook.player_filters(
            web_context=web_context,
            template_context=template_context,
        ):
            filters += plugin_filters
        filtered_players = [
            player
            for player in admin_event.players_by_id.values()
            if all(filter_(player) for filter_ in filters)
        ]
        search_results = [
            player.id for player in sorted(filtered_players, key=get_sort_key)
        ]
        SessionHandler.set_session_admin_players_search_results(request, search_results)
        return search_results

    @staticmethod
    def _matches_string_search(search: str, match: str):
        search_parts = search.split(' ')
        match_str = unicode_normalize(match.lower())
        return all(search_part in match_str for search_part in search_parts)

    @classmethod
    def _admin_event_players_render(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        modal: str | None = None,
        action: str | None = None,
        player_id: int | None = None,
        deleted_player_id: int | None = None,
        player_fide_id: int | None = None,
        player_from_plugin: Player | None = None,
        tournament_id: int | None = None,
        page: int | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            player_id=player_id,
            player_fide_id=player_fide_id,
            player_from_plugin=player_from_plugin,
            tournament_id=tournament_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context
        )
        admin_event: Event = web_context.admin_event
        search_results = SessionHandler.get_session_admin_players_search_results(
            request
        )
        if search_results is None:
            search_results = cls.set_players_search_results(request, event_uniq_id)
        players: dict[int, Player] = {}
        start_index = ((page or 1) - 1) * cls.PAGE_SIZE
        end_index = (page or 1) * cls.PAGE_SIZE
        pages = math.ceil(len(search_results) / cls.PAGE_SIZE)
        for index, player_id in enumerate(search_results[start_index:end_index]):
            if player := admin_event.players_by_id.get(player_id, None):
                players[start_index + index + 1] = player

        admin_player: Player | None = web_context.admin_player
        sharly_chess_config: SharlyChessConfig = SharlyChessConfig()

        # Allow plugin to provide extra columns
        per_plugin_columns: Iterable[Iterable[ExtraAdminColumn]] = (
            plugin_manager.hook.get_extra_player_columns()
        )
        extra_columns: dict[str, list[ExtraAdminColumn]] = {}
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
        # The clubs that will be shown on the club select list
        players_clubs: list[Club] = sorted(
            {
                player.club
                for player in web_context.admin_event.players_by_id.values()
                if player.club is not None
            }
        )
        # The genders that will be shown on the gender select list
        players_genders: list[PlayerGender] = sorted(
            {player.gender for player in web_context.admin_event.players_by_id.values()}
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
        # The categories that will be shown on the category select list
        players_categories: list[PlayerCategory] = sorted(
            {player.category for player in admin_event.players_by_id.values()}
        )

        per_plugin_context = plugin_manager.hook.get_player_admin_template_context(
            web_context=web_context
        )

        template_context |= {
            'admin_event_tab': 'admin-event-players-tab',
            'admin_players': players,
            'admin_filtered_player_count': len(search_results),
            'page': page or 1,
            'pages': pages,
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
            'player_updater_options': PlayerUpdaterManager.options(),
            'player_addable_tournaments': admin_event.player_addable_tournaments,
        } | {
            key: value
            for context in per_plugin_context
            for key, value in context.items()
        }

        match modal:
            case None:
                pass
            case 'player':
                federation_options = cls._get_federation_options(
                    sharly_chess_config.stored_config.federation
                    or SharlyChessConfig.default_federation
                )

                if data is None:
                    first_name: str | None = None
                    last_name: str | None = None
                    date_of_birth: date | None = None
                    gender: PlayerGender = PlayerGender.NONE
                    ratings: dict[TournamentRating, PlayerRating] = {
                        tr: PlayerRating(0, PlayerRatingType.ESTIMATED)
                        for tr in TournamentRating
                    }
                    title: PlayerTitle = PlayerTitle.NONE
                    federation: Federation | None = None
                    club: Club | None = None
                    fide_id: int | None = None
                    mail: str | None = None
                    phone: str | None = None
                    comment: str | None = None
                    owed: float = 0.0
                    paid: float = 0.0
                    fixed: int | None = None
                    plugin_data = {}
                    if admin_player:
                        first_name = admin_player.first_name
                        last_name = admin_player.last_name
                        gender = admin_player.gender
                        date_of_birth = admin_player.date_of_birth
                        ratings = admin_player.ratings
                        title = admin_player.title
                        federation = admin_player.federation
                        club = admin_player.club
                        fide_id = admin_player.fide_id or None
                        mail = admin_player.mail
                        phone = admin_player.phone
                        comment = admin_player.comment
                        owed = admin_player.owed or 0.0
                        paid = admin_player.paid or 0.0
                        fixed = admin_player.fixed
                        plugin_data = admin_player.plugin_data or {}
                    match action:
                        case 'update' | 'delete':
                            assert admin_player is not None
                            assert admin_player.tournament is not None
                            tournament_id = admin_player.tournament.id
                        case 'create':
                            if (
                                len(
                                    admin_event.not_finished_tournaments_with_file_sorted_by_uniq_id
                                )
                                == 1
                            ):
                                tournament_id = admin_event.not_finished_tournaments_with_file_sorted_by_uniq_id[
                                    0
                                ].id
                            else:
                                tournament_id = None
                        case _:
                            raise ValueError(f'action=[{action}]')

                    federation_options = cls._get_federation_options(
                        sharly_chess_config.stored_config.federation
                        or SharlyChessConfig.default_federation
                        if federation is None
                        else None
                    )

                    per_plugin_form_data = plugin_manager.hook.get_player_form_data(
                        plugin_data=plugin_data
                    )
                    plugin_form_data = {
                        key: value
                        for data in per_plugin_form_data
                        for key, value in data.items()
                    }

                    data = (
                        {
                            'last_name': WebContext.value_to_form_data(last_name),
                            'first_name': WebContext.value_to_form_data(first_name),
                            'gender': WebContext.value_to_form_data(gender.value),
                            'tournament_id': WebContext.value_to_form_data(
                                tournament_id
                            ),
                            'date_of_birth': WebContext.value_to_date_form_data(
                                date_of_birth
                            ),
                            'title': WebContext.value_to_form_data(title.value),
                            'federation': WebContext.value_to_form_data(federation),
                            'fide_id': WebContext.value_to_form_data(fide_id),
                            'club': WebContext.value_to_form_data(club),
                            'mail': WebContext.value_to_form_data(mail),
                            'phone': WebContext.value_to_form_data(phone),
                            'comment': WebContext.value_to_form_data(comment),
                            'owed': WebContext.value_to_form_data(owed),
                            'paid': WebContext.value_to_form_data(paid),
                            'fixed': WebContext.value_to_form_data(fixed or None),
                        }
                        | {
                            f'rating_{tr.value}': WebContext.value_to_form_data(
                                ratings[tr].value or None
                            )
                            for tr in TournamentRating
                        }
                        | {
                            f'rating_type_{tr.value}': WebContext.value_to_form_data(
                                ratings[tr].type.value
                            )
                            for tr in TournamentRating
                        }
                        | plugin_form_data
                    )
                if errors is None:
                    errors = {}
                tournaments = admin_event.player_addable_tournaments
                tournament_options: dict[str, str] = {}
                if action == 'create' and len(tournaments) > 1:
                    # force the choice of the tournament on player creation if several tournaments
                    tournament_options |= {'': '-'}
                elif action == 'update':
                    assert admin_player is not None
                    assert admin_player.tournament is not None
                    if admin_player.tournament not in tournaments:
                        tournaments.insert(0, admin_player.tournament)
                tournament_options |= {
                    str(tournament.id): f'{tournament.name} ({tournament.uniq_id})'
                    for tournament in tournaments
                }

                plugin_search_templates = (
                    plugin_manager.hook.get_player_search_template() or []
                )
                plugin_form_fields_templates = (
                    plugin_manager.hook.get_player_form_fields_template() or []
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
                    'rating_type_options': {
                        str(tr.value): tr.name for tr in PlayerRatingType
                    },
                    'title_options': {
                        str(t.value): f'{t.short_name} - {t.name}'
                        if t.short_name
                        else f'{t.name}'
                        for t in PlayerTitle
                    },
                    'licence_options': {
                        str(licence.value): licence.name for licence in PlayerFFELicence
                    },
                    'federation_options': federation_options,
                    'tournament_options': tournament_options,
                    'fide_search_available': FideDatabase().exists(),
                    'plugin_search_templates': plugin_search_templates,
                    'plugin_form_fields_templates': plugin_form_fields_templates,
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case 'record':
                assert admin_player is not None
                assert admin_player.tournament is not None
                data = {
                    f'round_{round_}_result': WebContext.value_to_form_data(
                        admin_player.pairings[round_].result.value
                    )  # type: ignore
                    for round_ in range(
                        max(1, admin_player.tournament.current_round),
                        admin_player.tournament.rounds + 1,
                    )
                }
                template_context |= {
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
            }

            return HTMXTemplate(
                template_name='/admin/players/table_header_and_player.html',
                context=template_context,
                re_target='#modal-wrapper',
                trigger_event='close_modal',
                after='receive',
            )

        if deleted_player_id is not None:
            print(f'deleted_player_id=[{deleted_player_id}]')
            template_context |= {
                'deleted_player_id': deleted_player_id,
            }
            return HTMXTemplate(
                template_name='/admin/players/table_header_and_player.html',
                context=template_context,
                re_target='#modal-wrapper',
                trigger_event='close_modal',
                after='receive',
            )

        if page:
            return HTMXTemplate(
                template_name='/admin/players/table_players_page.html',
                context=template_context,
            )

        return cls._admin_event_render(template_context)

    @get(
        path='/admin/event/{event_uniq_id:str}/players',
        name='admin-event-players-tab',
        cache=1,
    )
    async def htmx_admin_event_players_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        admin_players_sort: str | None = None,
        admin_players_filter_columns: list[str] | None = None,
        admin_players_filter_federations: list[str] | None = None,
        admin_players_filter_clubs: list[str] | None = None,
        admin_players_filter_clubs_search: str | None = None,
        admin_players_filter_genders: list[int] | None = None,
        admin_players_filter_check_ins: list[int] | None = None,
        admin_players_filter_tournaments: list[int] | None = None,
        admin_players_filter_categories: list[int] | None = None,
        admin_players_filter_name: str | None = None,
        admin_players_clear_filters: int | None = None,
    ) -> Template | ClientRedirect:
        if admin_players_sort is not None:
            SessionHandler.set_session_admin_players_sort(request, admin_players_sort)
        elif admin_players_filter_columns is not None:
            SessionHandler.set_session_admin_players_filter_columns(
                request,
                [
                    column
                    for column in admin_players_filter_columns
                    if column  # '' must be ignored
                ],
            )
        elif admin_players_filter_federations is not None:
            SessionHandler.set_session_admin_players_filter_federations(
                request,
                [
                    Federation.from_query_param(query_param)
                    for query_param in admin_players_filter_federations
                    if query_param != '*'
                ],
            )
        elif admin_players_filter_clubs is not None:
            SessionHandler.set_session_admin_players_filter_clubs(
                request,
                [
                    Club.from_query_param(query_param)
                    for query_param in admin_players_filter_clubs
                    if query_param != '*'
                ],
            )
        elif admin_players_filter_genders is not None:
            SessionHandler.set_session_admin_players_filter_genders(
                request,
                [
                    PlayerGender(query_param)
                    for query_param in admin_players_filter_genders
                    if query_param >= 0  # -1 must be ignored
                ],
            )
        elif admin_players_filter_check_ins is not None:
            SessionHandler.set_session_admin_players_filter_check_ins(
                request,
                [
                    {
                        0: None,
                        1: False,
                        2: True,
                    }.get(query_param, None)
                    for query_param in admin_players_filter_check_ins
                    if query_param >= 0  # -1 must be ignored
                ],
            )
        elif admin_players_filter_tournaments is not None:
            SessionHandler.set_session_admin_players_filter_tournaments(
                request,
                [
                    query_param
                    for query_param in admin_players_filter_tournaments
                    if query_param > 0  # 0 must be ignored
                ],
            )
        elif admin_players_filter_categories is not None:
            SessionHandler.set_session_admin_players_filter_categories(
                request,
                [
                    PlayerCategory(query_param)
                    for query_param in admin_players_filter_categories
                    if query_param >= 0  # -1 must be ignored
                ],
            )
        elif admin_players_filter_name is not None:
            SessionHandler.set_session_admin_players_filter_name(
                request, unicode_normalize(admin_players_filter_name).lower()
            )
        elif admin_players_filter_clubs_search is not None:
            SessionHandler.set_session_admin_players_filter_clubs_search(
                request, unicode_normalize(admin_players_filter_clubs_search).lower()
            )
        elif admin_players_clear_filters:
            SessionHandler.set_session_admin_players_filter_federations(request, [])
            SessionHandler.set_session_admin_players_filter_clubs(request, [])
            SessionHandler.set_session_admin_players_filter_genders(request, [])
            SessionHandler.set_session_admin_players_filter_check_ins(request, [])
            SessionHandler.set_session_admin_players_filter_tournaments(request, [])
            SessionHandler.set_session_admin_players_filter_categories(request, [])
            SessionHandler.set_session_admin_players_filter_name(request, '')
            SessionHandler.set_session_admin_players_filter_clubs_search(request, '')
            plugin_manager.hook.clear_player_filters(request=request)
        self.set_players_search_results(request, event_uniq_id)
        return self._admin_event_players_render(
            request,
            event_uniq_id=event_uniq_id,
        )

    @get(
        path='/admin/event/{event_uniq_id:str}/players/{page:int}',
        name='admin-event-players-page',
    )
    async def htmx_admin_event_players_page(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        page: int,
    ) -> Template | ClientRedirect:
        return self._admin_event_players_render(
            request,
            event_uniq_id=event_uniq_id,
            page=page,
        )

    @get(
        path='/admin/player-modal/create/{event_uniq_id:str}',
        name='admin-player-create-modal',
        cache=1,
    )
    async def htmx_admin_player_create_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_players_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='player',
            action='create',
        )

    @get(
        path='/admin/player-modal/create-from-fide/{event_uniq_id:str}/{player_fide_id:int}',
        name='admin-player-create-from-fide-modal',
        cache=1,
    )
    async def htmx_admin_player_create_from_fide_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        player_fide_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_players_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='player',
            action='create',
            player_fide_id=player_fide_id,
        )

    @get(
        path='/admin/player-modal/{action:str}/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-modal',
        cache=1,
    )
    async def htmx_admin_player_modal(
        self,
        request: HTMXRequest,
        action: str,
        event_uniq_id: str,
        player_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_players_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='player',
            action=action,
            player_id=player_id,
        )

    @get(
        path='/admin/record-modal/{event_uniq_id:str}/{player_id:int}',
        name='admin-record-modal',
        cache=1,
    )
    async def htmx_admin_record_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        player_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_players_render(
            request,
            event_uniq_id=event_uniq_id,
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
        event_uniq_id: str,
        player_id: int | None,
    ) -> Template | ClientRedirect:
        match action:
            case 'update' | 'create' | 'delete':
                web_context: PlayerAdminWebContext = PlayerAdminWebContext(
                    request,
                    event_uniq_id=event_uniq_id,
                    player_id=player_id,
                    player_fide_id=None,
                    player_from_plugin=None,
                    tournament_id=None,
                    data=data,
                )
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        player: Player = self._admin_validate_player_update_data(
            action, web_context, data
        )
        if player.errors:
            return self._admin_event_players_render(
                request,
                event_uniq_id=event_uniq_id,
                modal='player',
                action=action,
                player_id=player_id,
                player_fide_id=None,
                player_from_plugin=None,
                data=data,
                errors=player.errors,
            )
        match action:
            case 'update':
                assert player.tournament is not None
                assert web_context.admin_player is not None
                assert web_context.admin_player.tournament is not None

                plugin_manager.hook.set_player_default_ratings(
                    federation=web_context.admin_event.federation, player=player
                )
                previous_tournament = web_context.admin_player.tournament
                tournament = player.tournament
                if tournament.id != previous_tournament.id:
                    tournament.add_player(player)
                    previous_tournament.delete_player(player)
                else:
                    tournament.update_player(player)
            case 'create':
                assert player.tournament is not None
                plugin_manager.hook.set_player_default_ratings(
                    federation=web_context.admin_event.federation, player=player
                )
                tournament = player.tournament
                if tournament.finished:
                    Message.error(
                        request,
                        _(
                            'Tournament [{tournament_uniq_id}] is finished, you can not add players any longer.'
                        ).format(tournament_uniq_id=tournament.uniq_id),
                    )
                    return self._admin_event_players_render(
                        request,
                        event_uniq_id=event_uniq_id,
                        action=action,
                        data=data,
                    )
                if not tournament.file_exists:
                    Message.error(
                        request,
                        _(
                            'No Papi file found for tournament [{tournament_uniq_id}], can not add the player.'
                        ).format(tournament_uniq_id=tournament.uniq_id),
                    )
                    return self._admin_event_players_render(
                        request,
                        event_uniq_id=event_uniq_id,
                        modal='player',
                        action=action,
                        data=data,
                    )
                tournament.add_player(player)
            case 'delete':
                assert player.tournament is not None
                tournament = player.tournament
                if player.has_real_pairings:
                    Message.error(
                        request,
                        _(
                            'Player [{last_name} {first_name}] has pairings in tournament [{tournament_uniq_id}].'
                        ).format(
                            last_name=player.last_name,
                            first_name=player.first_name,
                            tournament_uniq_id=tournament.uniq_id,
                        ),
                    )
                else:
                    tournament.delete_player(player)
                    return self._admin_event_players_render(
                        request,
                        event_uniq_id=event_uniq_id,
                        deleted_player_id=player.id,
                    )
            case _:
                raise ValueError(f'action=[{action}]')
        return self._admin_event_players_render(
            request, event_uniq_id=event_uniq_id, player_id=player_id
        )

    @patch(
        path='/admin/player-move/{event_uniq_id:str}/{player_id:int}/{tournament_id:int}',
        name='admin-player-move',
    )
    async def htmx_admin_player_move(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        player_id: int,
        tournament_id: int,
    ) -> Template | ClientRedirect:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            player_id=player_id,
            player_fide_id=None,
            player_from_plugin=None,
            tournament_id=tournament_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        admin_player = web_context.admin_player
        dst_tournament = web_context.admin_tournament
        if admin_player is None:
            raise RuntimeError('admin_player not defined')
        if dst_tournament is None:
            raise RuntimeError('admin_tournament not defined')
        src_tournament = admin_player.tournament
        assert src_tournament is not None
        try:
            self._validate_player_tournament_move(admin_player, dst_tournament)
            dst_tournament.add_player(admin_player)
            src_tournament.delete_player(admin_player)
            Message.success(
                request,
                _(
                    'Player [{last_name} {first_name}] has been moved '
                    'from tournament [{src_tournament_uniq_id}] '
                    'to tournament [{dst_tournament_uniq_id}].'
                ).format(
                    last_name=admin_player.last_name,
                    first_name=admin_player.first_name,
                    src_tournament_uniq_id=src_tournament.uniq_id,
                    dst_tournament_uniq_id=dst_tournament.uniq_id,
                ),
            )
        except ValueError as e:
            Message.error(request, str(e))
        return self._admin_event_players_render(request, event_uniq_id=event_uniq_id)

    @staticmethod
    def _validate_player_tournament_move(player: Player, dst_tournament: Tournament):
        """Validate that a player can be moved from its current tournament to *dst_tournament*.
        Raises a ValueError if it is not possible."""

        src_tournament = player.tournament
        assert src_tournament is not None

        if player.has_real_pairings:
            raise ValueError(
                _(
                    'Player [{last_name} {first_name}] has pairings in tournament [{tournament_uniq_id}].'
                ).format(
                    last_name=player.last_name,
                    first_name=player.first_name,
                    tournament_uniq_id=src_tournament.uniq_id,
                ),
            )
        if not dst_tournament.file_exists:
            raise ValueError(
                _('Papi file [{tournament_file}] not found.').format(
                    tournament_file=dst_tournament.file
                ),
            )
        if not dst_tournament.can_add_players:
            raise ValueError(
                _(
                    'Impossible to add players to tournament [{tournament_uniq_id}].'
                ).format(tournament_uniq_id=src_tournament.uniq_id)
            )
        if player.fide_id in dst_tournament.players_by_fide_id:
            raise ValueError(
                _(
                    'Fide ID [{fide_id}] already present in tournament [{tournament_uniq_id}].'
                ).format(
                    fide_id=player.fide_id,
                    tournament_uniq_id=dst_tournament.uniq_id,
                ),
            )
        if plugin_error := (
            plugin_manager.hook.is_tournament_participation_possible(
                tournament=dst_tournament, player=player
            )
            or None
        ):
            raise ValueError(plugin_error)

    @post(path='/admin/player-create/{event_uniq_id:str}', name='admin-player-create')
    async def htmx_admin_player_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_player_update(
            request,
            event_uniq_id=event_uniq_id,
            action='create',
            player_id=None,
            data=data,
        )

    @patch(
        path='/admin/player-update/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-update',
    )
    async def htmx_admin_player_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        player_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_player_update(
            request,
            event_uniq_id=event_uniq_id,
            action='update',
            player_id=player_id,
            data=data,
        )

    @staticmethod
    def _new_byes(
        web_context: PlayerAdminWebContext,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> dict[int, Result]:
        """Returns a dict containing the byes that should be saved (changes only)."""
        new_byes: dict[int, Result] = {}
        assert web_context.admin_player is not None
        admin_player: Player = web_context.admin_player
        assert admin_player.tournament is not None
        admin_tournament: Tournament = admin_player.tournament
        pairings: dict[int, Pairing] = admin_player.pairings
        for round_ in range(
            max(1, admin_player.tournament.current_round),
            admin_player.tournament.rounds + 1,
        ):
            field = f'round_{round_}_result'
            if field in data:
                pairing: Pairing = pairings[round_]
                if not (
                    pairing.not_paired
                    or pairing.result
                    in [
                        Result.ZERO_POINT_BYE,
                        Result.HALF_POINT_BYE,
                        Result.FULL_POINT_BYE,
                    ]
                ):
                    logger.warning(
                        'Player [%s] already paired for round [%d].',
                        admin_player,
                        round_,
                    )
                    return {}
                result: Result = Result(int(data[field]))
                if result == pairings[round_].result:
                    continue
                match result:
                    case Result.ZERO_POINT_BYE | Result.NO_RESULT:
                        new_byes[round_] = result
                        continue
                    case Result.HALF_POINT_BYE | Result.FULL_POINT_BYE:
                        if (
                            round_
                            > admin_tournament.rounds
                            - admin_tournament.last_rounds_no_byes
                        ):
                            logger.warning('Bye not allowed for round [%d].', round_)
                            return {}
                        new_byes[round_] = result
                        continue
                    case _:
                        raise ValueError(f'{result=}')
        # check that the total number of byes is allowed
        byes: int = 0
        for round_ in pairings:
            match new_byes.get(round_, pairings[round_].result):
                case Result.HALF_POINT_BYE:
                    byes += 1
                case Result.FULL_POINT_BYE:
                    byes += 2
            if byes > admin_tournament.max_byes:
                logger.warning('Too many byes.')
                return {}
        return new_byes

    @patch(
        path='/admin/player-record/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-record',
    )
    async def htmx_admin_player_record(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        player_id: int,
    ) -> Template | ClientRedirect:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            player_id=player_id,
            player_fide_id=None,
            player_from_plugin=None,
            tournament_id=None,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_player is None:
            raise RuntimeError('admin_player not defined')
        if web_context.admin_player.tournament is None:
            raise RuntimeError('admin_player.tournament not defined')
        if new_byes := self._new_byes(web_context, data):
            web_context.admin_player.tournament.set_player_byes(
                web_context.admin_player, new_byes
            )
        return self._admin_event_players_render(request, event_uniq_id=event_uniq_id)

    @delete(
        path='/admin/player-delete/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_player_delete(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        player_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_player_update(
            request,
            event_uniq_id=event_uniq_id,
            action='delete',
            player_id=player_id,
            data=data,
        )

    @patch(
        path='/admin/tournament-open-check-in/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-open-check-in',
    )
    async def htmx_admin_tournament_open_check_in(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        tournament_id: int,
    ) -> Template | ClientRedirect:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            player_id=None,
            player_fide_id=None,
            player_from_plugin=None,
            tournament_id=tournament_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_tournament is None:
            raise RuntimeError('admin_tournament not defined')
        admin_tournament: Tournament = web_context.admin_tournament
        admin_tournament.open_check_in()
        Message.success(
            request,
            _('Check-in is open for tournament [{tournament_uniq_id}].').format(
                tournament_uniq_id=admin_tournament.uniq_id
            ),
        )
        return self._admin_event_players_render(request, event_uniq_id=event_uniq_id)

    @get(
        path='/admin/tournament-close-check-in-modal/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-close-check-in-modal',
        cache=1,
    )
    async def htmx_tournament_close_check_in_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_event_players_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='close_check_in',
            action=None,
            player_id=None,
            player_fide_id=None,
            player_from_plugin=None,
            tournament_id=tournament_id,
        )

    def _admin_tournament_close_check_in(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        tournament_id: int,
        zpbs_all_rounds: bool,
    ) -> Template | ClientRedirect:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            player_id=None,
            player_fide_id=None,
            player_from_plugin=None,
            tournament_id=tournament_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_tournament is None:
            raise RuntimeError('admin_tournament not defined')
        admin_tournament: Tournament = web_context.admin_tournament
        admin_tournament.close_check_in(zpbs_all_rounds)
        Message.success(
            request,
            _('Check-in is closed for tournament [{tournament_uniq_id}].').format(
                tournament_uniq_id=admin_tournament.uniq_id
            ),
        )
        return HTMXTemplate(
            template_name='common/empty.html',
            re_swap='none',
            trigger_event='request_refresh',
            after='receive',
        )

    @patch(
        path='/admin/tournament-close-check-in-zpb-next-round/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-close-check-in-zpb-next-round',
    )
    async def htmx_admin_tournament_close_check_in_zpb_next_round(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        tournament_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_tournament_close_check_in(
            request=request,
            data=data,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            zpbs_all_rounds=False,
        )

    @patch(
        path='/admin/tournament-close-check-in-zpb-last-rounds/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-close-check-in-zpb-last-rounds',
    )
    async def htmx_admin_close_tournament_check_in_zpbs_all_rounds(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        tournament_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_tournament_close_check_in(
            request=request,
            data=data,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            zpbs_all_rounds=True,
        )

    def _admin_player_check_in_out(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        player_id: int,
        check_in: bool,
    ) -> Template | ClientRedirect:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            player_id=player_id,
            player_fide_id=None,
            player_from_plugin=None,
            tournament_id=None,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_player is None:
            raise RuntimeError('admin_player not defined')
        admin_player: Player = web_context.admin_player
        if admin_player.tournament is None:
            raise RuntimeError('admin_player.tournament not defined')
        admin_player.tournament.check_in_player(admin_player, check_in)
        return self._admin_event_players_render(
            request, event_uniq_id=event_uniq_id, player_id=player_id
        )

    @patch(
        path='/admin/player-check-in/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-check-in',
    )
    async def htmx_admin_player_check_in(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        player_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_player_check_in_out(
            request=request,
            data=data,
            event_uniq_id=event_uniq_id,
            player_id=player_id,
            check_in=True,
        )

    @patch(
        path='/admin/player-check-out/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-check-out',
    )
    async def htmx_admin_player_check_out(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        player_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_player_check_in_out(
            request=request,
            data=data,
            event_uniq_id=event_uniq_id,
            player_id=player_id,
            check_in=False,
        )

    @patch(
        path='/admin/players-update/{event_uniq_id:str}/{player_updater_id:str}',
        name='admin-event-players-update',
    )
    async def htmx_admin_update_event_players(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        player_updater_id: str,
        tournament_id: int | None = None,
    ) -> Template | ClientRedirect | Redirect:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request, event_uniq_id=event_uniq_id, tournament_id=tournament_id
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        try:
            player_updater: PlayerUpdater = PlayerUpdaterManager.get_object(
                player_updater_id
            )
        except KeyError:
            return self.redirect_error(
                request, f'Unknown data source [{player_updater_id}].'
            )
        plugin_updater_field_ids: list[str] = [
            field.id for field in player_updater.fields()
        ]
        field_ids: list[str] = [
            field_id
            for field_id in data['field_ids']
            if field_id in plugin_updater_field_ids
        ]
        players: list[Player] = [
            web_context.admin_event.players_by_id[player_id]
            for player_id in map(int, (id_ for id_ in data['player_ids'] if id_))
        ]
        player_matches = await player_updater.get_player_matches(
            players, field_ids, diff_only=True
        )
        if player_matches is None:
            Message.error(
                request,
                _('Could not connect to data source [{player_updater_name}].').format(
                    player_updater_name=player_updater.name
                ),
            )
        else:
            for match in player_matches:
                match.update_player_from_match(field_ids)

            players_by_tournament_id: dict[int, list[Player]] = defaultdict(
                list[Player]
            )
            for player_match in player_matches:
                players_by_tournament_id[player_match.player.tournament_id].append(
                    player_match.player
                )
            for tournament_id, tournament_players in players_by_tournament_id.items():
                tournament: Tournament = web_context.admin_event.tournaments_by_id[
                    tournament_id
                ]
                with tournament.papi_write_database as database:
                    for player in tournament_players:
                        database.update_player(player)
                    database.commit()

            count: int = len(player_matches)
            Message.success(
                request,
                ngettext(
                    '{count} player updated.', '{count} players updated.', count
                ).format(count=count)
                if count
                else _('No players updated.'),
            )
        return self._admin_event_players_render(request, event_uniq_id=event_uniq_id)

    @get(
        path='/admin/event-players-diff-modal/{event_uniq_id:str}/{player_updater_id:str}',
        name='admin-event-players-diff-modal',
    )
    async def htmx_admin_event_players_diff_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        player_updater_id: str,
        tournament_id: int | None = None,
    ) -> Template | ClientRedirect | Redirect:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request, event_uniq_id=event_uniq_id, tournament_id=tournament_id
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        try:
            player_updater: PlayerUpdater = PlayerUpdaterManager.get_object(
                player_updater_id
            )
        except KeyError:
            # should never happen, not translated
            return self.redirect_error(
                request, f'Unknown data source [{player_updater_id}].'
            )
        field_ids: list[str] = [field.id for field in player_updater.fields()]
        players = (
            web_context.admin_tournament.players_by_name_with_unpaired
            if web_context.admin_tournament
            else web_context.admin_event.players_sorted_by_name
        )
        player_matches: (
            list[PlayerComparator] | None
        ) = await player_updater.get_player_matches(players, field_ids, diff_only=False)
        template_context: dict[str, Any] = self._get_admin_event_render_context(
            web_context
        )
        if player_matches is None:
            Message.error(
                request,
                _('Could not connect to data source [{player_updater_name}].').format(
                    player_updater_name=player_updater.name
                ),
            )
            return self._admin_event_players_render(
                request, event_uniq_id=event_uniq_id
            )

        per_plugin_columns: Iterable[Iterable[ExtraAdminColumn]] = (
            plugin_manager.hook.get_extra_players_update_columns()
        )
        extra_columns: dict[str, list[ExtraAdminColumn]] = {}
        for plugin_columns in per_plugin_columns:
            for extra_column in plugin_columns:
                c = extra_columns.setdefault(extra_column.at, [])
                c.append(extra_column)

        template_context |= {
            'modal': 'players_diff',
            'player_updater': player_updater,
            'field_ids': field_ids,
            'player_matches': player_matches,
            'update_enabled': any(
                player_match.diff_field_ids for player_match in player_matches
            ),
            'admin_players_update_extra_columns': extra_columns,
        }
        return self._admin_event_render(template_context)
