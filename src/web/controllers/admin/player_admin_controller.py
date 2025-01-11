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
from web.controllers.admin.event_admin_controller import EventAdminWebContext, AbstractEventAdminController
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

    """
    @classmethod
    def _admin_validate_tournament_update_data(
            cls,
            action: str,
            web_context: TournamentAdminWebContext,
            data: dict[str, str] | None = None,
    ) -> StoredTournament:
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        uniq_id: str = WebContext.form_data_to_str(data, 'uniq_id')
        if action == 'delete':
            if not uniq_id:
                errors['uniq_id'] = _('Please enter the tournament ID.')
            elif uniq_id != web_context.admin_tournament.uniq_id:
                errors['uniq_id'] = _('tournament ID does not match.')
        else:
            if not uniq_id:
                errors['uniq_id'] = _('Please enter the tournament ID.')
            elif uniq_id.find('/') != -1:
                errors['uniq_id'] = _('Character [{char}] is not allowed.').format(char='/')
            else:
                match action:
                    case 'create' | 'clone':
                        if uniq_id in web_context.admin_event.tournaments_by_uniq_id:
                            errors['uniq_id'] = _('Tournament [{uniq_id}] already exists.').format(uniq_id=uniq_id)
                    case 'update':
                        if uniq_id != web_context.admin_tournament.uniq_id \
                                and uniq_id in web_context.admin_event.tournaments_by_uniq_id:
                            errors['uniq_id'] = _('Tournament [{uniq_id}] already exists.').format(uniq_id=uniq_id)
                    case _:
                        raise ValueError(f'action=[{action}]')
        name: str | None = None
        path: str | None = None
        filename: str | None = None
        ffe_id: int | None = None
        ffe_password: str | None = None
        time_control_initial_time: int | None = None
        time_control_increment: int | None = None
        time_control_handicap_penalty_value: int | None = None
        time_control_handicap_penalty_step: int | None = None
        time_control_handicap_min_time: int | None = None
        chessevent_id: int | None = None
        chessevent_tournament_name: str | None = None
        record_illegal_moves: int | None = None
        rules: str | None = None
        match action:
            case 'create' | 'update' | 'clone':
                name = WebContext.form_data_to_str(data, 'name')
                if not name:
                    errors['name'] = _('Please enter the tournament name.')
                path = WebContext.form_data_to_str(data, 'path')
                filename = WebContext.form_data_to_str(data, 'filename')
                try:
                    ffe_id = WebContext.form_data_to_int(data, 'ffe_id')
                except ValueError:
                    errors['ffe_id'] = _('The FFE ID is a positive integer.')
                ffe_password = WebContext.form_data_to_str(data, 'ffe_password')
                if ffe_password and not re.match('^[A-Z]{10}$', ffe_password):
                    errors['ffe_password'] = _(
                        'The password of the tournament on the FFE website is made of 10 uppercase letters.')
                time_control_initial_time = WebContext.form_data_to_int(data, 'time_control_initial_time')
                time_control_increment = WebContext.form_data_to_int(data, 'time_control_increment')
                time_control_handicap_penalty_value = WebContext.form_data_to_int(
                    data, 'time_control_handicap_penalty_value')
                time_control_handicap_penalty_step = WebContext.form_data_to_int(
                    data, 'time_control_handicap_penalty_step')
                time_control_handicap_min_time = WebContext.form_data_to_int(
                    data, 'time_control_handicap_min_time')
                chessevent_id = WebContext.form_data_to_int(data, 'chessevent_id')
                chessevent_tournament_name = WebContext.form_data_to_str(data, 'chessevent_tournament_name')
                record_illegal_moves = cls._admin_validate_record_illegal_moves_update_data(data, errors)
                rules = cls._admin_validate_rules_update_data(data, errors)
            case 'delete':
                pass
            case _:
                raise ValueError(f'action=[{action}]')
        return StoredTournament(
            id=web_context.admin_tournament.id if action not in ['create', 'clone', ] else None,
            uniq_id=uniq_id,
            name=name,
            path=path,
            filename=filename,
            ffe_id=ffe_id,
            ffe_password=ffe_password,
            time_control_initial_time=time_control_initial_time,
            time_control_increment=time_control_increment,
            time_control_handicap_penalty_value=time_control_handicap_penalty_value,
            time_control_handicap_penalty_step=time_control_handicap_penalty_step,
            time_control_handicap_min_time=time_control_handicap_min_time,
            chessevent_id=chessevent_id,
            chessevent_tournament_name=chessevent_tournament_name,
            record_illegal_moves=record_illegal_moves,
            rules=rules,
            errors=errors,
        )
    """

    """
    @staticmethod
    def _get_chessevent_options(admin_event: Event) -> dict[str, str]:
        options: dict[str, str] = {
            '': 'Pas de connexion à ChessEvent',
        }
        for chessevent in admin_event.chessevents_by_id.values():
            options[str(chessevent.id)] = (f' {chessevent.uniq_id} ({chessevent.user_id}'
                                           f'/{chessevent.shadowed_password}/{chessevent.event_id})')
        return options
    """

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
                """
            case 'player':
                if data is None:
                    uniq_id: str | None = None
                    name: str | None = None
                    match action:
                        case 'update':
                            uniq_id = web_context.admin_tournament.stored_tournament.uniq_id
                            name = web_context.admin_tournament.stored_tournament.name
                        case 'create':
                            uniq_id = web_context.admin_event.get_unused_tournament_uniq_id(_('tournament'))
                            name = web_context.admin_event.get_unused_tournament_name(_('New tournament'))
                        case 'clone':
                            uniq_id = web_context.admin_event.get_unused_tournament_uniq_id(
                                web_context.admin_tournament.stored_tournament.uniq_id)
                            name = web_context.admin_event.get_unused_tournament_name(
                                web_context.admin_tournament.stored_tournament.name)
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    path: str | None = None
                    filename: str | None = None
                    ffe_id: int | None = None
                    ffe_password: str | None = None
                    time_control_initial_time: int | None = None
                    time_control_increment: int | None = None
                    time_control_handicap_penalty_value: int | None = None
                    time_control_handicap_penalty_step: int | None = None
                    time_control_handicap_min_time: int | None = None
                    chessevent_id: int | None = None
                    chessevent_tournament_name: str | None = None
                    record_illegal_moves: int | None = None
                    rules: str | None = None
                    match action:
                        case 'update' | 'clone':
                            path = web_context.admin_tournament.stored_tournament.path
                            time_control_initial_time = web_context.admin_tournament.stored_tournament.time_control_initial_time
                            time_control_increment = web_context.admin_tournament.stored_tournament.time_control_increment
                            time_control_handicap_penalty_value = web_context.admin_tournament.stored_tournament.time_control_handicap_penalty_value
                            time_control_handicap_penalty_step = web_context.admin_tournament.stored_tournament.time_control_handicap_penalty_step
                            time_control_handicap_min_time = web_context.admin_tournament.stored_tournament.time_control_handicap_min_time
                            chessevent_id = web_context.admin_tournament.stored_tournament.chessevent_id
                            chessevent_tournament_name = web_context.admin_tournament.stored_tournament.chessevent_tournament_name
                            record_illegal_moves = web_context.admin_tournament.stored_tournament.record_illegal_moves
                            rules = web_context.admin_tournament.stored_tournament.rules
                        case 'create' | 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    match action:
                        case 'update':
                            filename = web_context.admin_tournament.stored_tournament.filename
                            ffe_id = web_context.admin_tournament.stored_tournament.ffe_id
                            ffe_password = web_context.admin_tournament.stored_tournament.ffe_password
                        case 'clone' | 'create' | 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    data = {
                        'uniq_id': WebContext.value_to_form_data(uniq_id),
                        'name': WebContext.value_to_form_data(name),
                        'path': WebContext.value_to_form_data(path),
                        'filename': WebContext.value_to_form_data(filename),
                        'time_control_initial_time': WebContext.value_to_form_data(time_control_initial_time),
                        'time_control_increment': WebContext.value_to_form_data(time_control_increment),
                        'time_control_handicap_penalty_value': WebContext.value_to_form_data(time_control_handicap_penalty_value),
                        'time_control_handicap_penalty_step': WebContext.value_to_form_data(time_control_handicap_penalty_step),
                        'time_control_handicap_min_time': WebContext.value_to_form_data(time_control_handicap_min_time),
                        'chessevent_id': WebContext.value_to_form_data(chessevent_id),
                        'chessevent_tournament_name': WebContext.value_to_form_data(chessevent_tournament_name),
                        'record_illegal_moves': WebContext.value_to_form_data(record_illegal_moves),
                        'rules': WebContext.value_to_form_data(rules),
                        'ffe_id': WebContext.value_to_form_data(ffe_id),
                        'ffe_password': WebContext.value_to_form_data(ffe_password),
                    }
                    stored_tournament: StoredTournament = cls._admin_validate_tournament_update_data(
                        action, web_context, data)
                    errors = stored_tournament.errors
                if errors is None:
                    errors = {}
                template_context |= {
                    'chessevent_options': cls._get_chessevent_options(web_context.admin_event),
                    'record_illegal_moves_options': cls._get_record_illegal_moves_options(
                        web_context.admin_event.record_illegal_moves),
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            """
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

    """
    @get(
        path='/admin/tournament-modal/{action:str}/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-modal',
        cache=1,
    )
    async def htmx_admin_tournament_modal(
            self, request: HTMXRequest,
            action: str,
            event_uniq_id: str,
            tournament_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_tournaments_render(
            request, event_uniq_id=event_uniq_id, modal='tournament', action=action, tournament_id=tournament_id)
    """

    def _admin_player_update(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            action: str,
            event_uniq_id: str,
            player_id: int | None,
    ) -> Template | ClientRedirect:
        match action:
            case 'update' | 'delete' | 'clone' | 'create':
                web_context: PlayerAdminWebContext = PlayerAdminWebContext(
                    request, event_uniq_id=event_uniq_id, player_id=player_id, tournament_id=None, data=data)
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        """
        stored_tournament: StoredTournament = self._admin_validate_tournament_update_data(
            action, web_context, data)
        if stored_tournament.errors:
            return self._admin_event_tournaments_render(
                request, event_uniq_id=event_uniq_id, modal='tournament', action=action, tournament_id=tournament_id,
                data=data, errors=stored_tournament.errors)
        event_loader: EventLoader = EventLoader.get(request=request)
        with (EventDatabase(web_context.admin_event.uniq_id, write=True) as event_database):
            match action:
                case 'create' | 'clone':
                    stored_tournament = event_database.add_stored_tournament(stored_tournament)
                    if 'add_screens' in data:
                        for (type, menu, name) in [
                            ('input', '@input', _('Results entry'), ),
                            ('boards', '@boards', _('Pairings by board'), ),
                            ('players', '@players', _('Pairings by player'), ),
                        ]:
                            stored_screen: StoredScreen = event_database.add_stored_screen(StoredScreen(
                                id=None,
                                uniq_id=web_context.admin_event.get_unused_screen_uniq_id(
                                    f'{stored_tournament.uniq_id}-{type}'),
                                type='input',
                                public=True,
                                name=name,
                                columns=1,
                                menu_link=True,
                                menu_text=None,
                                menu=menu,
                                timer_id=None,
                                input_exit_button=None,
                                players_show_unpaired=None,
                                results_limit=None,
                                results_max_age=None,
                                results_tournament_ids=[],
                                background_image=None,
                                background_color=None,
                                message_default=True,
                                message_text=None,
                            ))
                            event_database.add_stored_screen_set(stored_screen.id, stored_tournament.id)
                    event_database.commit()
                    if 'add_screens' in data:
                        Message.success(
                            request,
                            _('Tournament [{tournament_uniq_id}] has been created and default screens have been '
                              'added.').format(tournament_uniq_id=stored_tournament.uniq_id))
                    else:
                        Message.success(
                            request,
                            _('Tournament [{tournament_uniq_id}] has been created.').format(
                                tournament_uniq_id=stored_tournament.uniq_id))
                    event_loader.clear_cache(event_uniq_id)
                    return self._admin_event_tournaments_render(request, event_uniq_id=event_uniq_id)
                case 'update':
                    stored_tournament = event_database.update_stored_tournament(stored_tournament)
                    event_database.commit()
                    Message.success(
                        request,
                        _('Tournament [{tournament_uniq_id}] has been updated.').format(
                            tournament_uniq_id=stored_tournament.uniq_id))
                    event_loader.clear_cache(event_uniq_id)
                    return self._admin_event_tournaments_render(request, event_uniq_id=event_uniq_id)
                case 'delete':
                    event_database.delete_stored_tournament(web_context.admin_tournament.id)
                    event_database.commit()
                    Message.success(
                        request,
                        _('Tournament [{tournament_uniq_id}] has been deleted.').format(
                            tournament_uniq_id=web_context.admin_tournament.uniq_id))
                    event_loader.clear_cache(event_uniq_id)
                    return self._admin_event_tournaments_render(request, event_uniq_id=event_uniq_id)
                case _:
                    raise ValueError(f'action=[{action}]')
        """
        return web_context.error

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
