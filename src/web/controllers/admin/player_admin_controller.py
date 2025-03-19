import string
from datetime import date
from logging import Logger
from typing import Annotated, Any

from common import unicode_normalize
from litestar import get, patch, delete, post
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common.i18n import _
from common.logger import get_logger
from common.papi_web_config import PapiWebConfig
from data.event import Event
from data.loader import EventLoader
from data.pairing import Pairing
from data.player import Player, Federation, Club
from data.tournament import Tournament
from data.util import (
    PlayerCategory,
    PlayerGender,
    TournamentRating,
    PlayerRatingType,
    PlayerTitle,
    Result,
)
from database.sqlite.fide.fide_database import FideDatabase
from plugins.ffe.util import PlayerFFELicence
from plugins.manager import plugin_manager
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
        player_id: int | None,
        player_fide_id: int | None,
        player_from_plugin: Player | None,
        tournament_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ]
        | None,
    ):
        super().__init__(
            request, event_uniq_id=event_uniq_id, data=data
        )
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
            with FideDatabase() as fide_database:
                self.admin_player = fide_database.get_player_by_fide_id(player_fide_id)
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
    @classmethod
    def _admin_validate_player_update_data(
        cls,
        action: str,
        web_context: PlayerAdminWebContext,
        data: dict[str, str] | None = None,
    ) -> Player:
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        field: str = ''
        if action in [
            'delete',
        ]:
            return web_context.admin_player
        tournament: Tournament | None = None
        match action:
            case 'create':
                try:
                    tournament = web_context.admin_event.tournaments_by_id[
                        WebContext.form_data_to_int(data, field := 'tournament_id')
                    ]
                except (ValueError, KeyError):
                    errors[field] = _('Please choose the tournament.')
            case 'update':
                tournament = web_context.admin_player.tournament
            case _:
                raise ValueError(f'action={action}')
        last_name: str | None = WebContext.form_data_to_str(data, field := 'last_name')
        if not last_name:
            errors[field] = _('Please enter the last name.')
        else:
            last_name = last_name.upper()
        first_name: str | None = WebContext.form_data_to_str(
            data, 'first_name'
        )
        if first_name:
            first_name = string.capwords(first_name)
        date_of_birth: date | None = WebContext.form_data_to_date(
            data, field := 'date_of_birth'
        )
        if not date_of_birth:
            errors[field] = _('Please enter the date of birth.')
        gender: PlayerGender | None = PlayerGender.NONE
        try:
            gender = PlayerGender(WebContext.form_data_to_int(data, field := 'gender'))
        except ValueError:
            # should never happen, not translated.
            errors[field] = f'Invalid gender value [{data[field]}].'
            data[field] = ''
        field: str = 'rating_type'
        rating_types: dict[TournamentRating, PlayerRatingType] = {
            tr: PlayerRatingType(
                WebContext.form_data_to_int(data, f'{field}_{tr.value}')
            )
            for tr in TournamentRating
        }
        field: str = 'rating'
        ratings: dict[TournamentRating, int] = {
            tr: WebContext.form_data_to_int(data, f'{field}_{tr.value}')
            for tr in TournamentRating
        }
        for tr in TournamentRating:
            if rating_types[tr] != PlayerRatingType.ESTIMATED and not ratings[tr]:
                errors[f'{field}_{tr.value}'] = _(
                    'Only estimated ratings are optional.'
                )
        title: PlayerTitle | None = PlayerTitle.NONE
        try:
            title = PlayerTitle(WebContext.form_data_to_int(data, field := 'title'))
        except ValueError:
            # should never happen, not translated.
            errors[field] = f'Invalid title value [{data[field]}].'
            data[field] = ''
        federation_name: str | None = WebContext.form_data_to_str(
            data, field := 'federation', PapiWebConfig().default_federation
        )
        federation: Federation | None = None
        if federation_name not in PapiWebConfig.federations:
            # should never happen, not translated.
            errors[field] = f'Invalid federation value [{data[field]}].'
            data[field] = ''
        else:
            federation = Federation(federation_name)
        club_name: str | None = WebContext.form_data_to_str(data, field := 'club')
        club: Club = Club(club_name) if club_name else None
        fide_id: int | None = None
        try:
            fide_id = WebContext.form_data_to_int(data, field := 'fide_id', minimum=1)
            if action == 'create' and tournament and fide_id and fide_id in tournament.players_by_fide_id:
                errors[field] = _(
                    'The player with FIDE ID [{fide_id}] already plays tournament [{tournament_uniq_id}].'
                ).format(
                    fide_id=fide_id,
                    tournament_uniq_id=tournament.uniq_id
                )
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
        plugin_data = { key: value for data in per_plugin_player_data for key, value in data.items() }

        return Player(
            id=web_context.admin_player.id if action != 'create' else None,
            first_name=first_name,
            last_name=last_name,
            date_of_birth=date_of_birth,
            gender=gender,
            mail=mail,
            phone=phone,
            comment=comment,
            owed=owed,
            paid=paid,
            title=title,
            ratings=ratings,
            rating_types=rating_types,
            fide_id=fide_id,
            federation=federation,
            club=club,
            fixed=fixed,
            check_in=False,  # not taken into account when updating/creating/deleting the player
            pairings={},  # Pairings are read from Papi but not used
            tournament=tournament,
            errors=errors,
            plugin_data=plugin_data
        )

    @staticmethod
    def _get_gender_options() -> dict[str, str]:
        return {WebContext.value_to_form_data(gender.value): gender.name for gender in PlayerGender}

    @classmethod
    def _admin_event_players_render(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        modal: str | None = None,
        action: str | None = None,
        player_id: int | None = None,
        player_fide_id: int | None = None,
        player_from_plugin: Player | None = None,
        tournament_id: int | None = None,
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
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context
        )
        admin_event: Event = web_context.admin_event
        admin_player: Player = web_context.admin_player
        
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
        
        per_plugin_context = plugin_manager.hook.get_player_admin_template_context(web_context=web_context)
        plugin_context =  {key: value for context in per_plugin_context for key, value in context.items()}

        template_context |= plugin_context
        
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
                    and all(plugin_manager.hook.filter_player(
                        web_context=web_context,
                        template_context=template_context,
                        player=player
                    ))
                ],
                key=sort_key,
            )
        }
        
        template_context |= {
            'admin_event_tab': 'admin-event-players-tab',
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
        
        match modal:
            case None:
                pass
            case 'player':
                if data is None:
                    first_name: str | None = None
                    last_name: str | None = None
                    date_of_birth: float | None = None
                    gender: PlayerGender = PlayerGender.NONE
                    ratings: dict[TournamentRating, int] = {
                        tr: 0 for tr in TournamentRating
                    }
                    rating_types: dict[TournamentRating, PlayerRatingType] = {
                        tr: PlayerRatingType.ESTIMATED for tr in TournamentRating
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
                    fixed: int = 0
                    plugin_data = {}
                    if admin_player:
                        first_name = admin_player.first_name
                        last_name = admin_player.last_name
                        gender = admin_player.gender
                        date_of_birth = admin_player.date_of_birth
                        ratings = admin_player.ratings
                        rating_types = admin_player.rating_types
                        title = admin_player.title
                        federation = admin_player.federation
                        club = admin_player.club
                        fide_id = admin_player.fide_id or None
                        mail = admin_player.mail
                        phone = admin_player.phone
                        comment = admin_player.comment
                        owed = admin_player.owed
                        paid = admin_player.paid
                        fixed = admin_player.fixed
                        plugin_data = admin_player.plugin_data or {}
                    match action:
                        case 'update' | 'delete':
                            tournament_id = admin_player.tournament.id
                        case 'create':
                            if len(admin_event.not_finished_tournaments_with_file_sorted_by_uniq_id) == 1:
                                tournament_id = admin_event.not_finished_tournaments_with_file_sorted_by_uniq_id[0].id
                            else:
                                tournament_id = None
                        case _:
                            raise ValueError(f'action=[{action}]')

                    per_plugin_form_data = plugin_manager.hook.get_player_form_data(plugin_data=plugin_data)
                    plugin_form_data = { key: value for data in per_plugin_form_data for key, value in data.items() }

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
                                ratings[tr] or None
                            )
                            for tr in TournamentRating
                        }
                        | {
                            f'rating_type_{tr.value}': WebContext.value_to_form_data(
                                rating_types[tr].value
                            )
                            for tr in TournamentRating
                        }
                        | plugin_form_data
                    )
                if errors is None:
                    errors = {}
                federation_ids: list[str] = [
                    admin_event.federation,
                ] + [
                    federation_id
                    for federation_id in PapiWebConfig.federations
                    if federation_id != admin_event.federation
                ]
                tournament_options: dict[str, str] = (
                    {  # force the choice of the tournament on player creation if several tournaments
                        '': '-',
                    } if (
                        action == 'create' and
                        len(admin_event.not_finished_tournaments_with_file_sorted_by_uniq_id) > 1
                    ) else {
                    }
                ) | {
                    str(tournament.id): f'{tournament.name} ({tournament.uniq_id})'
                    for tournament in admin_event.not_finished_tournaments_with_file_sorted_by_uniq_id
                }

                plugin_search_templates = plugin_manager.hook.get_player_search_template() or []
                plugin_form_fields_templates = plugin_manager.hook.get_player_form_fields_template() or []

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
                    'tournament_options': tournament_options,
                    'federations': {
                        federation_id: PapiWebConfig.federations[federation_id]
                        for federation_id in federation_ids
                    },
                    'fide_search_available': FideDatabase().exists(),
                    'plugin_search_templates': plugin_search_templates,
                    'plugin_form_fields_templates': plugin_form_fields_templates,
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case 'record':
                data = {
                    f'round_{round_}_result': WebContext.value_to_form_data(
                        admin_player.pairings[round_].result.value)
                    for round_ in range(
                        max(1, admin_player.tournament.current_round),
                        admin_player.tournament.rounds + 1)
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
            SessionHandler.set_session_admin_players_sort(
                request, admin_players_sort
            )
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
                    if query_param  # '' must be ignored
                ],
            )
        elif admin_players_filter_clubs is not None:
            SessionHandler.set_session_admin_players_filter_clubs(
                request,
                [
                    Club.from_query_param(query_param)
                    for query_param in admin_players_filter_clubs
                    if query_param  # '' must be ignored
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
            SessionHandler.set_session_admin_players_filter_federations(
                request, []
            )
            SessionHandler.set_session_admin_players_filter_clubs(request, [])
            SessionHandler.set_session_admin_players_filter_genders(request, [])
            SessionHandler.set_session_admin_players_filter_check_ins(
                request, []
            )
            SessionHandler.set_session_admin_players_filter_tournaments(
                request, []
            )
            SessionHandler.set_session_admin_players_filter_categories(
                request, []
            )
            SessionHandler.set_session_admin_players_filter_name(request, '')
            SessionHandler.set_session_admin_players_filter_clubs_search(request, '')
            plugin_manager.hook.clear_player_filters(request=request)
        return self._admin_event_players_render(
            request,
            event_uniq_id=event_uniq_id,
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
                plugin_manager.hook.set_player_default_ratings(
                    federation=web_context.admin_event.federation,
                    player=player
                )
                tournament: Tournament = player.tournament
                tournament.update_player(player)
                event_loader: EventLoader = EventLoader.get(request=request)
                event_loader.clear_cache(event_uniq_id)
            case 'create':
                plugin_manager.hook.set_player_default_ratings(
                    federation=web_context.admin_event.federation,
                    player=player
                )
                tournament: Tournament = player.tournament
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
                event_loader: EventLoader = EventLoader.get(request=request)
                event_loader.clear_cache(event_uniq_id)
            case 'delete':
                tournament: Tournament = player.tournament
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
                    event_loader: EventLoader = EventLoader.get(request=request)
                    event_loader.clear_cache(event_uniq_id)
            case _:
                raise ValueError(f'action=[{action}]')
        return self._admin_event_players_render(request, event_uniq_id=event_uniq_id)

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
        admin_player: Player = web_context.admin_player
        src_tournament: Tournament = admin_player.tournament

        if admin_player.has_real_pairings:
            Message.error(
                request,
                _(
                    'Player [{last_name} {first_name}] has pairings in tournament [{tournament_uniq_id}].'
                ).format(
                    last_name=admin_player.last_name,
                    first_name=admin_player.first_name,
                    tournament_uniq_id=src_tournament.uniq_id,
                ),
            )
        else:
            dst_tournament: Tournament = web_context.admin_tournament

            if not dst_tournament.file_exists:
                Message.error(
                    request,
                    _('Papi file [{tournament_file}] not found.').format(
                        tournament_file=dst_tournament.file
                    ),
                )
            elif admin_player.fide_id in dst_tournament.players_by_fide_id:
                Message.error(
                    request,
                    _(
                        'Fide ID [{fide_id}] already present in tournament [{tournament_uniq_id}].'
                    ).format(
                        fide_id=admin_player.fide_id,
                        tournament_uniq_id=dst_tournament.uniq_id,
                    ),
                )
            elif plugin_error := (plugin_manager.hook.is_tournament_participation_possible(
                tournament=dst_tournament, player=admin_player
            ) or None):
                Message.error(request, plugin_error)
            else:
                dst_tournament.add_player(admin_player)
                src_tournament.delete_player(admin_player)
                Message.success(
                    request,
                    _(
                        'Player [{last_name} {first_name}] has been moved from tournament [{src_tournament_uniq_id}] to tournament [{dst_tournament_uniq_id}].'
                    ).format(
                        last_name=admin_player.last_name,
                        first_name=admin_player.first_name,
                        src_tournament_uniq_id=src_tournament.uniq_id,
                        dst_tournament_uniq_id=dst_tournament.uniq_id,
                    ),
                )
                event_loader: EventLoader = EventLoader.get(request=request)
                event_loader.clear_cache(event_uniq_id)
        return self._admin_event_players_render(request, event_uniq_id=event_uniq_id)

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
        admin_player: Player = web_context.admin_player
        admin_tournament: Tournament = admin_player.tournament
        pairings: dict[int, Pairing] = admin_player.pairings
        for round_ in range(
            max(1, admin_player.tournament.current_round),
            admin_player.tournament.rounds + 1
        ):
            field: str = f'round_{round_}_result'
            if field in data:
                pairing: Pairing = pairings[round_]
                if not(pairing.not_paired or pairing.result in [
                    Result.ZERO_POINT_BYE, Result.HALF_POINT_BYE, Result.FULL_POINT_BYE,
                ]):
                    logger.warning(
                        'Player [%s] already paired for round [%d].',
                        admin_player, round_
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
                        if round_ > admin_tournament.rounds - admin_tournament.last_rounds_no_byes:
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
        if new_byes := self._new_byes(web_context, data):
            web_context.admin_player.tournament.set_player_byes(web_context.admin_player, new_byes)
            event_loader: EventLoader = EventLoader.get(request=request)
            event_loader.clear_cache(event_uniq_id)
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
        admin_tournament: Tournament = web_context.admin_tournament
        admin_tournament.open_check_in()
        Message.success(
            request,
            _('Check-in is open for tournament [{tournament_uniq_id}].').format(
                tournament_uniq_id=admin_tournament.uniq_id
            ),
        )
        event_loader: EventLoader = EventLoader.get(request=request)
        event_loader.clear_cache(event_uniq_id)
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
        forfeit_all_rounds: bool,
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
        admin_tournament: Tournament = web_context.admin_tournament
        admin_tournament.close_check_in(forfeit_all_rounds)
        Message.success(
            request,
            _('Check-in is closed for tournament [{tournament_uniq_id}].').format(
                tournament_uniq_id=admin_tournament.uniq_id
            ),
        )
        event_loader: EventLoader = EventLoader.get(request=request)
        event_loader.clear_cache(event_uniq_id)
        return self._admin_event_players_render(request, event_uniq_id=event_uniq_id)

    @patch(
        path='/admin/tournament-close-check-in-forfeit-next-round/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-close-check-in-forfeit-next-round',
    )
    async def htmx_admin_tournament_close_check_in_forfeit_next_round(
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
            forfeit_all_rounds=False,
        )

    @patch(
        path='/admin/tournament-close-check-in-forfeit-last-rounds/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-close-check-in-forfeit-last-rounds',
    )
    async def htmx_admin_close_tournament_check_in_forfeit_all_rounds(
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
            forfeit_all_rounds=True,
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
        admin_player: Player = web_context.admin_player
        admin_player.tournament.check_in_player(admin_player, check_in)
        event_loader: EventLoader = EventLoader.get(request=request)
        event_loader.clear_cache(event_uniq_id)
        return self._admin_event_players_render(request, event_uniq_id=event_uniq_id)

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
