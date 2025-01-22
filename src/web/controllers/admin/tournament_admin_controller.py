import re
from logging import Logger
from tempfile import NamedTemporaryFile
from typing import Annotated, Any

import trf
from litestar import post, get, delete, patch
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, File
from litestar.status_codes import HTTP_200_OK

from common.i18n import _
from common.logger import get_logger
from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from data.util import TrfType
from database.sqlite import EventDatabase
from database.store import StoredTournament, StoredScreen
from web.controllers.admin.event_admin_controller import EventAdminWebContext, AbstractEventAdminController
from web.controllers.index_controller import WebContext
from web.messages import Message

logger: Logger = get_logger()


class TournamentAdminWebContext(EventAdminWebContext):
    def __init__(
            self, request: HTMXRequest,
            event_uniq_id: str,
            admin_event_tab: str | None,
            tournament_id: int | None,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ] | None,
    ):
        super().__init__(request, event_uniq_id=event_uniq_id, admin_event_tab=admin_event_tab, data=data)
        self.admin_tournament: Tournament | None = None
        if self.error:
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
            'admin_tournament': self.admin_tournament,
        }


class TournamentAdminController(AbstractEventAdminController):

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
        check_in_open: bool = False
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
                        check_in_open = web_context.admin_tournament.check_in_open
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
            check_in_open=check_in_open,
            errors=errors,
        )

    @staticmethod
    def _get_chessevent_options(admin_event: Event) -> dict[str, str]:
        options: dict[str, str] = {
            '': _('No ChessEvent connection'),
        }
        for chessevent in admin_event.chessevents_by_id.values():
            options[str(chessevent.id)] = (f' {chessevent.uniq_id} ({chessevent.user_id}'
                                           f'/{chessevent.shadowed_password}/{chessevent.event_id})')
        return options

    @classmethod
    def _admin_event_tournaments_render(
            cls,
            request: HTMXRequest,
            event_uniq_id: str,
            modal: str | None = None,
            action: str | None = None,
            tournament_id: int | None = None,
            data: dict[str, str] | None = None,
            errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: TournamentAdminWebContext = TournamentAdminWebContext(
            request, event_uniq_id=event_uniq_id, admin_event_tab='tournaments', tournament_id=tournament_id, data=data)
        if web_context.error:
            return web_context.error
        admin_event: Event = web_context.admin_event
        admin_tournament: Tournament = web_context.admin_tournament
        template_context: dict[str, Any] = cls._get_admin_event_render_context(web_context)
        match modal:
            case None:
                pass
            case 'tournament':
                if data is None:
                    uniq_id: str | None = None
                    name: str | None = None
                    match action:
                        case 'update':
                            uniq_id = admin_tournament.stored_tournament.uniq_id
                            name = admin_tournament.stored_tournament.name
                        case 'create':
                            uniq_id = admin_event.get_unused_tournament_uniq_id(_('tournament'))
                            name = admin_event.get_unused_tournament_name(_('New tournament'))
                        case 'clone':
                            uniq_id = admin_event.get_unused_tournament_uniq_id(
                                admin_tournament.stored_tournament.uniq_id)
                            name = admin_event.get_unused_tournament_name(admin_tournament.stored_tournament.name)
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
                            time_control_initial_time = admin_tournament.stored_tournament.time_control_initial_time
                            time_control_increment = admin_tournament.stored_tournament.time_control_increment
                            time_control_handicap_penalty_value = \
                                admin_tournament.stored_tournament.time_control_handicap_penalty_value
                            time_control_handicap_penalty_step = \
                                admin_tournament.stored_tournament.time_control_handicap_penalty_step
                            time_control_handicap_min_time = \
                                admin_tournament.stored_tournament.time_control_handicap_min_time
                            chessevent_id = admin_tournament.stored_tournament.chessevent_id
                            chessevent_tournament_name = admin_tournament.stored_tournament.chessevent_tournament_name
                            record_illegal_moves = admin_tournament.stored_tournament.record_illegal_moves
                            rules = admin_tournament.stored_tournament.rules
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
                        'time_control_handicap_penalty_value': WebContext.value_to_form_data(
                            time_control_handicap_penalty_value),
                        'time_control_handicap_penalty_step': WebContext.value_to_form_data(
                            time_control_handicap_penalty_step),
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
                    'chessevent_options': cls._get_chessevent_options(admin_event),
                    'record_illegal_moves_options': cls._get_record_illegal_moves_options(
                        admin_event.record_illegal_moves),
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case _:
                raise ValueError(f'modal=[{modal}]')
        return cls._admin_event_render(template_context)

    @get(
        path='/admin/tournament-modal/create/{event_uniq_id:str}',
        name='admin-tournament-create-modal',
        cache=1,
    )
    async def htmx_admin_tournament_create_modal(
            self, request: HTMXRequest,
            event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_tournaments_render(
            request, event_uniq_id=event_uniq_id, modal='tournament', action='create', tournament_id=None)

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

    @get(
        path='/admin/tournament-trf-export/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-trf-export',
    )
    async def admin_tournament_trf_export(
            self,
            request: HTMXRequest,
            event_uniq_id: str,
            tournament_id: int,
            usage: TrfType = TrfType.PAIRING,
    ) -> File:
        context = TournamentAdminWebContext(request, event_uniq_id, None, tournament_id, None)
        tournament = context.admin_tournament
        temp_file = NamedTemporaryFile(delete=False, mode="w", suffix=".trf")
        with temp_file as file:
            trf.dump(file, tournament.to_trf(usage))
        return File(path=temp_file.name, filename=f'{tournament.name}.{usage.file_extension}')

    def _admin_tournament_update(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            action: str,
            event_uniq_id: str,
            tournament_id: int | None,
    ) -> Template | ClientRedirect:
        match action:
            case 'update' | 'delete' | 'clone' | 'create':
                web_context: TournamentAdminWebContext = TournamentAdminWebContext(
                    request, event_uniq_id=event_uniq_id, admin_event_tab='tournaments', tournament_id=tournament_id,
                    data=data)
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
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
                                type=type,
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

    @patch(
        path='/admin/tournament-update/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-update'
    )
    async def htmx_admin_tournament_update(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
            tournament_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_tournament_update(
            request, event_uniq_id=event_uniq_id, action='update', tournament_id=tournament_id, data=data)

    @delete(
        path='/admin/tournament-delete/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_tournament_delete(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
            tournament_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_tournament_update(
            request, event_uniq_id=event_uniq_id, action='delete', tournament_id=tournament_id, data=data)
