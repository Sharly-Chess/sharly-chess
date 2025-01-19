import re
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
from common.papi_web_config import PapiWebConfig
from data.loader import EventLoader
from data.player import Player
from data.tournament import Tournament
from data.util import PlayerGender, TournamentRating, PlayerRatingType, PlayerTitle, PlayerFFELicence
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
        self.admin_tournament: Tournament | None = None
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
            'admin_tournament': self.admin_tournament,
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
        last_name: str | None = None
        first_name: str | None = None
        date_of_birth: date | None = None
        gender: PlayerGender | None = PlayerGender.NONE
        ratings: dict[TournamentRating, int] = {tr: 0 for tr in TournamentRating}
        rating_types: dict[TournamentRating, PlayerRatingType] = {
            tr: PlayerRatingType.ESTIMATED for tr in TournamentRating
        }
        title: PlayerTitle | None = PlayerTitle.NONE
        federation: str | None = None
        league: str | None = None
        club: str | None = None
        fide_id: int | None = None
        ffe_id: int | None = None
        ffe_licence: PlayerFFELicence = PlayerFFELicence.NONE
        ffe_licence_number: str | None = None
        mail: str | None = None
        phone: str | None = None
        owed: float | None = 0.0
        paid: float | None = 0.0
        comment: str | None = None
        if action in ['delete', ]:
            pass
        else:
            last_name = WebContext.form_data_to_str(data, field := 'last_name')
            if not last_name:
                errors[field] = _('Please enter the last name.')
            else:
                last_name = last_name.upper()
            first_name = WebContext.form_data_to_str(data, field := 'first_name')
            if first_name:
                first_name = string.capwords(first_name)
            date_of_birth = WebContext.form_data_to_date(data, field := 'date_of_birth')
            if not date_of_birth:
                errors[field] = _('Please enter the date of birth.')
            try:
                gender = PlayerGender(WebContext.form_data_to_int(data, field := 'gender'))
            except ValueError:
                # should never happen, not translated.
                errors[field] = f'Invalid gender value [{data[field]}].'
                data[field] = ''
            field: str = 'rating'
            ratings = {
                tr: WebContext.form_data_to_int(data, f'{field}_{tr.value}')
                for tr in TournamentRating
            }
            field: str = 'rating_type'
            rating_types = {
                tr: PlayerRatingType(WebContext.form_data_to_int(data, f'{field}_{tr.value}'))
                for tr in TournamentRating
            }
            try:
                title = PlayerTitle(WebContext.form_data_to_int(data, field := 'title'))
            except ValueError:
                # should never happen, not translated.
                errors[field] = f'Invalid title value [{data[field]}].'
                data[field] = ''
            federation = WebContext.form_data_to_str(data, field := 'federation')
            if not federation in PapiWebConfig.federations:
                # should never happen, not translated.
                errors[field] = f'Invalid federation value [{data[field]}].'
                data[field] = ''
            league = WebContext.form_data_to_str(data, field := 'league')
            if league and not league in PapiWebConfig.ffe_leagues:
                # should never happen, not translated.
                errors[field] = f'Invalid league value [{data[field]}].'
                data[field] = ''
            club = WebContext.form_data_to_str(data, field := 'club')
            try:
                fide_id = WebContext.form_data_to_int(data, field := 'fide_id', minimum=1)
            except ValueError:
                errors[field] = _('Invalid FIDE ID [{fide_id}].').format(fide_id=data[field])
            try:
                ffe_id = WebContext.form_data_to_int(data, field := 'ffe_id', minimum=1)
            except ValueError:
                errors[field] = _('Invalid FFE ID [{ffe_id}].').format(fide_id=data[field])
            try:
                ffe_licence = PlayerFFELicence(WebContext.form_data_to_int(data, field := 'ffe_licence'))
            except ValueError:
                errors[field] = f'Invalid FFE licence [{data[field]}].'
            ffe_licence_number = WebContext.form_data_to_str(data, field := 'ffe_licence_number')
            if not re.match(r'^[A-Z]\d{5}$', ffe_licence_number):
                errors[field] = f'Invalid FFE licence [{data[field]}].'
            try:
                mail = WebContext.form_data_to_mail(data, field := 'mail')
            except ValueError:
                errors[field] = _('Invalid mail [{mail}].').format(mail=data[field])
            try:
                phone = WebContext.form_data_to_phone(data, field := 'phone')
            except ValueError:
                errors[field] = _('Invalid phone number [{phone}].').format(phone=data[field])
            try:
                owed = WebContext.form_data_to_float(data, field := 'owed')
            except ValueError:
                errors[field] = f'Invalid amount [{data[field]}].'
            try:
                paid = WebContext.form_data_to_float(data, field := 'paid')
            except ValueError:
                errors[field] = f'Invalid amount [{data[field]}].'
            comment = WebContext.form_data_to_mail(data, 'comment')
        return Player(
            id=web_context.admin_player.id,
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
            ffe_id=ffe_id,
            ffe_licence=ffe_licence,
            ffe_licence_number=ffe_licence_number,
            federation=federation,
            league=league,
            club=club,
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
            tournament_id: int | None = None,
            data: dict[str, str] | None = None,
            errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request, event_uniq_id=event_uniq_id, player_id=player_id, tournament_id=tournament_id, data=data)
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
                    federation: str | None = None
                    fide_id: int | None = None
                    league: str | None = None
                    club: str | None = None
                    ffe_licence: PlayerFFELicence = PlayerFFELicence.NONE
                    ffe_licence_number: str | None = None
                    ffe_id: int | None = None
                    mail: str | None = None
                    phone: str | None = None
                    comment: str | None = None
                    owed: float = 0.0
                    paid: float = 0.0
                    match action:
                        case 'update' | 'delete':
                            first_name = web_context.admin_player.first_name
                            last_name = web_context.admin_player.last_name
                            gender = web_context.admin_player.gender
                            date_of_birth = web_context.admin_player.date_of_birth
                            ratings = web_context.admin_player.ratings
                            rating_types = web_context.admin_player.rating_types
                            fide_id = web_context.admin_player.fide_id
                            title = web_context.admin_player.title
                            federation = web_context.admin_player.federation
                            league = web_context.admin_player.league
                            club = web_context.admin_player.club
                            ffe_licence = web_context.admin_player.ffe_licence
                            ffe_licence_number = web_context.admin_player.ffe_licence_number
                            ffe_id = web_context.admin_player.ffe_id
                            mail = web_context.admin_player.mail
                            phone = web_context.admin_player.phone
                            comment = web_context.admin_player.comment
                            owed = web_context.admin_player.owed
                            paid = web_context.admin_player.paid
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
                        'federation': WebContext.value_to_form_data(federation),
                        'fide_id': WebContext.value_to_form_data(fide_id),
                        'league': WebContext.value_to_form_data(league),
                        'club': WebContext.value_to_form_data(club),
                        'ffe_licence': WebContext.value_to_form_data(ffe_licence),
                        'ffe_licence_number': WebContext.value_to_form_data(ffe_licence_number),
                        'ffe_id': WebContext.value_to_form_data(ffe_id),
                        'mail': WebContext.value_to_form_data(mail),
                        'phone': WebContext.value_to_form_data(phone),
                        'comment': WebContext.value_to_form_data(comment),
                        'owed': WebContext.value_to_form_data(owed),
                        'paid': WebContext.value_to_form_data(paid),
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
                    'title_options': {str(t.value): f'{t.short_name} - {t.name}' if t.short_name else f'{t.name}' for t in PlayerTitle},
                    'licence_options': {str(l.value): l.name for l in PlayerFFELicence},
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case 'close_check_in':
                template_context |= {
                    'modal': modal,
                }
                pass
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
            case 'update' | 'create' | 'delete':
                web_context: PlayerAdminWebContext = PlayerAdminWebContext(
                    request, event_uniq_id=event_uniq_id, player_id=player_id, tournament_id=None, data=data)
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        player: Player = self._admin_validate_player_update_data(action, web_context, data)
        if player.errors:
            return self._admin_event_players_render(
                request, event_uniq_id=event_uniq_id, modal='player', action=action, player_id=player_id,
                data=data, errors=player.errors)
        match action:
            case 'update':
                tournament: Tournament = player.tournament
                tournament.update_player(player)
                event_loader: EventLoader = EventLoader.get(request=request)
                event_loader.clear_cache(event_uniq_id)
            case 'create':
                raise ValueError(f'action=[{action}]')
            case 'delete':
                tournament: Tournament = player.tournament
                if player.has_real_pairings:
                    Message.error(
                        request,
                        _('Player [{last_name} {first_name}] has pairings in tournament [{tournament_uniq_id}].').format(
                            last_name=player.last_name, first_name=player.first_name,
                            tournament_uniq_id=tournament.uniq_id))
                else:
                    tournament.delete_player(player.ref_id, return_deleted_data=False)
                    event_loader: EventLoader = EventLoader.get(request=request)
                    event_loader.clear_cache(event_uniq_id)
            case _:
                raise ValueError(f'action=[{action}]')
        return self._admin_event_players_render(request, event_uniq_id=event_uniq_id)

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
                    tournament_uniq_id=src_tournament.uniq_id))
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
        return self._admin_player_update(
            request, event_uniq_id=event_uniq_id, action='delete', player_id=player_id, data=data)

    @patch(
        path='/admin/tournament-open-check-in/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-open-check-in',
    )
    async def htmx_admin_tournament_open_check_in(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
            tournament_id: int,
    ) -> Template | ClientRedirect:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request, event_uniq_id=event_uniq_id, player_id=None, tournament_id=tournament_id, data=data)
        if web_context.error:
            return web_context.error
        admin_tournament: Tournament = web_context.admin_tournament
        admin_tournament.open_check_in()
        Message.success(
            request,
            _('Check-in is open for tournament [{tournament_uniq_id}].').format(
                tournament_uniq_id=admin_tournament.uniq_id))
        event_loader: EventLoader = EventLoader.get(request=request)
        event_loader.clear_cache(event_uniq_id)
        return self._admin_event_players_render(request, event_uniq_id=event_uniq_id)

    @get(
        path='/admin/tournament-close-check-in-modal/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-close-check-in-modal',
        cache=1,
    )
    async def htmx_tournament_close_check_in_modal(
            self, request: HTMXRequest,
            event_uniq_id: str,
            tournament_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_event_players_render(
            request, event_uniq_id=event_uniq_id, modal='close_check_in', action=None, player_id=None,
            tournament_id=tournament_id)

    def _admin_tournament_close_check_in(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
            tournament_id: int,
            forfeit_all_rounds: bool,
    ) -> Template | ClientRedirect:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request, event_uniq_id=event_uniq_id, player_id=None, tournament_id=tournament_id, data=data)
        if web_context.error:
            return web_context.error
        admin_tournament: Tournament = web_context.admin_tournament
        admin_tournament.close_check_in(forfeit_all_rounds)
        Message.success(
            request,
            _('Check-in is closed for tournament [{tournament_uniq_id}].').format(
                tournament_uniq_id=admin_tournament.uniq_id))
        event_loader: EventLoader = EventLoader.get(request=request)
        event_loader.clear_cache(event_uniq_id)
        return self._admin_event_players_render(request, event_uniq_id=event_uniq_id)

    @patch(
        path='/admin/tournament-close-check-in-forfeit-next-round/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-close-check-in-forfeit-next-round',
    )
    async def htmx_admin_tournament_close_check_in_forfeit_next_round(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
            tournament_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_tournament_close_check_in(
            request=request, data=data, event_uniq_id=event_uniq_id, tournament_id=tournament_id,
            forfeit_all_rounds=False)

    @patch(
        path='/admin/tournament-close-check-in-forfeit-last-rounds/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-close-check-in-forfeit-last-rounds',
    )
    async def htmx_admin_close_tournament_check_in_forfeit_all_rounds(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
            tournament_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_tournament_close_check_in(
            request=request, data=data, event_uniq_id=event_uniq_id, tournament_id=tournament_id,
            forfeit_all_rounds=True)

    def _admin_player_check_in_out(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
            player_id: int,
            check_in: bool,
    ) -> Template | ClientRedirect:
        web_context: PlayerAdminWebContext = PlayerAdminWebContext(
            request, event_uniq_id=event_uniq_id, player_id=player_id, tournament_id=None, data=data)
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
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
            player_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_player_check_in_out(
            request=request, data=data, event_uniq_id=event_uniq_id, player_id=player_id, check_in=True)

    @patch(
        path='/admin/player-check-out/{event_uniq_id:str}/{player_id:int}',
        name='admin-player-check-out',
    )
    async def htmx_admin_player_check_out(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
            player_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_player_check_in_out(
            request=request, data=data, event_uniq_id=event_uniq_id, player_id=player_id, check_in=False)
