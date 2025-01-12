import string
from datetime import date
from logging import Logger
from typing import Annotated, Any

from litestar import get, patch, delete
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common.i18n import _
from common.logger import get_logger
from data.loader import EventLoader
from data.player import Player
from data.tournament import Tournament
from data.util import PlayerGender, TournamentRating, PlayerRatingType, PlayerTitle
from web.controllers.admin.event_admin_controller import EventAdminWebContext, AbstractEventAdminController
from web.controllers.index_controller import WebContext
from web.messages import Message

logger: Logger = get_logger()


class PlayerAdminWebContext(EventAdminWebContext):
    def __init__(
            self, request: HTMXRequest,
            event_uniq_id: str,
            player_id: int | None,
            tournament_id: int | None,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ] | None,
    ):
        super().__init__(request, event_uniq_id=event_uniq_id, admin_event_tab='players', data=data)
        self.admin_player: Player | None = None
        if self.error:
            return
        if player_id:
            try:
                self.admin_player = self.admin_event.players_by_id[player_id]
            except KeyError:
                self._redirect_error(f'Player [{player_id}] not found.')
                return
        if tournament_id:
            try:
                self.admin_tournament = self.admin_event.tournaments_by_id[tournament_id]
            except KeyError:
                self._redirect_error(f'Tournament [{tournament_id}] not found.')
                return

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_player': self.admin_player,
        }


class PlayerAdminController(AbstractEventAdminController):

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
        field: str = 'last_name'
        last_name: str = WebContext.form_data_to_str(data, field)
        if not last_name:
            errors[field] = _('Please enter the last name.')
        else:
            last_name = last_name.upper()
        field: str = 'first_name'
        first_name: str = WebContext.form_data_to_str(data, field)
        if not first_name:
            errors[field] = _('Please enter the first name.')
        else:
            first_name = string.capwords(first_name)
        field: str = 'date_of_birth'
        date_of_birth: date | None = WebContext.form_data_to_date(data, field)
        if not date_of_birth:
            errors[field] = _('Please enter the date of birth.')
        field: str = 'gender'
        gender: PlayerGender | None = PlayerGender.NONE
        try:
            gender = PlayerGender(WebContext.form_data_to_int(data, field))
        except ValueError:
            # should never happen, not translated.
            errors[field] = f'Invalid gender value [{data[field]}].'
            data[field] = ''
        field: str = 'rating'
        ratings: dict[TournamentRating, int] = {
            tr: WebContext.form_data_to_int(data, f'{field}_{tr.value}')
            for tr in TournamentRating
        }
        field: str = 'rating_type'
        rating_types: dict[TournamentRating, PlayerRatingType] = {
            tr: PlayerRatingType(WebContext.form_data_to_int(data, f'{field}_{tr.value}'))
            for tr in TournamentRating
        }
        field: str = 'title'
        title: PlayerTitle | None = PlayerTitle.NONE
        try:
            title = PlayerTitle(WebContext.form_data_to_int(data, field))
        except ValueError:
            # should never happen, not translated.
            errors[field] = f'Invalid title value [{data[field]}].'
            data[field] = ''
        return Player(
            id=web_context.admin_player.id,
            first_name=first_name,
            last_name=last_name,
            date_of_birth=date_of_birth,
            gender=gender,
            mail=web_context.admin_player.mail,
            phone=web_context.admin_player.phone,
            comment=web_context.admin_player.comment,
            owed=web_context.admin_player.owed,
            paid=web_context.admin_player.paid,
            title=title,
            ratings=ratings,
            rating_types=rating_types,
            fide_id=web_context.admin_player.ffe_id,
            ffe_id=web_context.admin_player.ffe_id,
            ffe_licence=web_context.admin_player.ffe_licence,
            ffe_licence_number=web_context.admin_player.ffe_licence_number,
            federation=web_context.admin_player.federation,
            league=web_context.admin_player.league,
            club=web_context.admin_player.club,
            fixed=web_context.admin_player.fixed,
            check_in=web_context.admin_player.check_in,
            pairings=web_context.admin_player.pairings,
            tournament=web_context.admin_player.tournament,
            errors=errors,
        )

    @staticmethod
    def _get_gender_options() -> dict[str, str]:
        return {str(gender.value): gender.name for gender in PlayerGender}

    @classmethod
    def _admin_event_players_render(
            cls,
            request: HTMXRequest,
            event_uniq_id: str,
            modal: str | None = None,
            action: str | None = None,
            player_id: int | None = None,
            data: dict[str, str] | None = None,
            errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request, event_uniq_id=event_uniq_id, player_id=player_id, tournament_id=None, data=data)
        if web_context.error:
            return web_context.error
        template_context: dict[str, Any] = cls._get_admin_event_render_context(web_context)
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
                    match action:
                        case 'update':
                            first_name = web_context.admin_player.first_name
                            last_name = web_context.admin_player.last_name
                            gender = web_context.admin_player.gender
                            date_of_birth = web_context.admin_player.date_of_birth
                            ratings = web_context.admin_player.ratings
                            rating_types = web_context.admin_player.rating_types
                            title = web_context.admin_player.title
                        case 'create':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    data = {
                        'last_name': WebContext.value_to_form_data(last_name),
                        'first_name': WebContext.value_to_form_data(first_name),
                        'gender': WebContext.value_to_form_data(gender.value),
                        'date_of_birth': WebContext.value_to_date_form_data(date_of_birth),
                        'title': WebContext.value_to_form_data(title.value),
                    } | {
                        f'rating_{tr.value}': WebContext.value_to_form_data(ratings[tr])
                        for tr in TournamentRating
                    } | {
                        f'rating_type_{tr.value}': WebContext.value_to_form_data(rating_types[tr].value)
                        for tr in TournamentRating
                    }
                    player: Player = cls._admin_validate_player_update_data(action, web_context, data)
                    errors = player.errors
                if errors is None:
                    errors = {}
                template_context |= {
                    'gender_options': cls._get_gender_options(),
                    'tournament_ratings_strings': {
                        TournamentRating.STANDARD: {
                            'label': _('Standard:'),
                            'help': _('The rating used when the time control is at least 60 minutes.'),
                        },
                        TournamentRating.RAPID: {
                            'label': _('Rapid:'),
                            'help': _('The rating used when the time control is more than 10 minutes and less than 60 minutes.'),
                        },
                        TournamentRating.BLITZ: {
                            'label': _('Blitz:'),
                            'help': _('The rating used when the time control is at most 10 minutes.'),
                        },
                    },
                    'rating_type_options': {str(tr.value): tr.name for tr in PlayerRatingType},
                    'title_options': {str(t.value): t.name for t in PlayerTitle},
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case _:
                raise ValueError(f'modal=[{modal}]')
        return cls._admin_event_render(template_context)

    @get(
        path='/admin/player-modal/create/{event_uniq_id:str}',
        name='admin-player-create-modal',
        cache=1,
    )
    async def htmx_admin_player_create_modal(
            self, request: HTMXRequest,
            event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_players_render(
            request, event_uniq_id=event_uniq_id, modal='player', action='create', player_id=None)

    @get(
        path='/admin/player-modal/{action:str}/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-modal',
        cache=1,
    )
    async def htmx_admin_player_modal(
            self, request: HTMXRequest,
            action: str,
            event_uniq_id: str,
            player_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_players_render(
            request, event_uniq_id=event_uniq_id, modal='player', action=action, player_id=player_id)

    def _admin_player_update(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            action: str,
            event_uniq_id: str,
            player_id: int | None,
    ) -> Template | ClientRedirect:
        match action:
            case 'update' | 'create':
                web_context: PlayerAdminWebContext = PlayerAdminWebContext(
                    request, event_uniq_id=event_uniq_id, player_id=player_id, tournament_id=None, data=data)
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        player: Player = self._admin_validate_player_update_data(action, web_context, data)
        if player.errors:
            Message.error(request, list(player.errors.values()))
            return self._admin_event_players_render(
                request, event_uniq_id=event_uniq_id, modal='player', action=action, player_id=player_id,
                data=data, errors=player.errors)
        tournament: Tournament = player.tournament
        tournament.update_player(player)
        Message.success(request, 'OK')
        event_loader: EventLoader = EventLoader.get(request=request)
        event_loader.clear_cache(event_uniq_id)
        return self._admin_event_players_render(request, event_uniq_id=event_uniq_id)

    """
    @post(
        path='/admin/tournament-create/{event_uniq_id:str}',
        name='admin-tournament-create'
    )
    async def htmx_admin_tournament_create(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_tournament_update(
            request, event_uniq_id=event_uniq_id, action='create', tournament_id=None, data=data)
    """

    @patch(
        path='/admin/player-move/{event_uniq_id:str}/{player_id:int}/{tournament_id:int}',
        name='admin-player-move'
    )
    async def htmx_admin_player_move(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
            player_id: int,
            tournament_id: int,
    ) -> Template | ClientRedirect:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request, event_uniq_id=event_uniq_id, player_id=player_id, tournament_id=tournament_id, data=data)
        if web_context.error:
            return web_context.error
        admin_player: Player = web_context.admin_player
        src_tournament: Tournament = admin_player.tournament
        if admin_player.has_real_pairings:
            Message.error(
                request,
                _('Player [{last_name} {first_name}] has pairings in tournament [{tournament_uniq_id}].').format(
                    last_name=admin_player.last_name, first_name=admin_player.first_name,
                    tournament_uniq_id=src_tournament))
        else:
            dst_tournament: Tournament = web_context.admin_tournament
            if not dst_tournament.file_exists:
                Message.error(
                    request,
                    _('Papi file [{tournament_file}] not found.').format(tournament_file=dst_tournament.file))
            elif admin_player.ffe_licence_number in dst_tournament.players_by_ffe_licence_number:
                Message.error(
                    request,
                    _('FFE licence [{ffe_licence_number}] already present in tournament [{tournament_uniq_id}].').format(
                        ffe_licence_number=admin_player.ffe_licence_number, tournament_uniq_id=dst_tournament.uniq_id))
            elif admin_player.fide_id in dst_tournament.players_by_fide_id:
                Message.error(
                    request,
                    _('Fide ID [{fide_id}] already present in tournament [{tournament_uniq_id}].').format(
                        fide_id=admin_player.fide_id, tournament_uniq_id=dst_tournament.uniq_id))
            elif admin_player.ffe_id in dst_tournament.players_by_ffe_id:
                # This string is not translated because the error should never happen
                Message.error(
                    request,
                    f'FFE ID [{admin_player.ffe_id}] already present in tournament [{dst_tournament.uniq_id}].')
            else:
                player_dict: dict[str, str | int | float | None] = src_tournament.delete_player(
                    admin_player.ref_id, return_deleted_data=True)
                dst_tournament.add_player_from_dict(player_dict)
                Message.success(
                    request,
                    _('Player [{last_name} {first_name}] has been moved from tournament [{src_tournament_uniq_id}] to tournament [{dst_tournament_uniq_id}].').format(
                        last_name=admin_player.last_name, first_name=admin_player.first_name,
                        src_tournament_uniq_id=src_tournament.uniq_id,
                        dst_tournament_uniq_id=dst_tournament.uniq_id))
                event_loader: EventLoader = EventLoader.get(request=request)
                event_loader.clear_cache(event_uniq_id)
        return self._admin_event_players_render(request, event_uniq_id=event_uniq_id)

    @patch(
        path='/admin/player-update/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-update'
    )
    async def htmx_admin_player_update(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
            player_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_player_update(
            request, event_uniq_id=event_uniq_id, action='update', player_id=player_id, data=data)

    @delete(
        path='/admin/player-delete/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_player_delete(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
            player_id: int,
    ) -> Template | ClientRedirect:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request, event_uniq_id=event_uniq_id, player_id=player_id, tournament_id=None, data=data)
        if web_context.error:
            return web_context.error
        admin_player: Player = web_context.admin_player
        src_tournament: Tournament = admin_player.tournament
        if admin_player.has_real_pairings:
            Message.error(
                request,
                _('Player [{last_name} {first_name}] has pairings in tournament [{tournament_uniq_id}].').format(
                    last_name=admin_player.last_name, first_name=admin_player.first_name,
                    tournament_uniq_id=src_tournament))
        else:
            src_tournament.delete_player(admin_player.ref_id, return_deleted_data=False)
            Message.success(
                request,
                _('Player [{last_name} {first_name}] has been removed from tournament [{tournament_uniq_id}].').format(
                    last_name=admin_player.last_name, first_name=admin_player.first_name,
                    tournament_uniq_id=admin_player.tournament.uniq_id))
            event_loader: EventLoader = EventLoader.get(request=request)
            event_loader.clear_cache(event_uniq_id)
        return self._admin_event_players_render(request, event_uniq_id=event_uniq_id)
