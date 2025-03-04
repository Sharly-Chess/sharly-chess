import re
from logging import Logger
from tempfile import NamedTemporaryFile
from typing import Annotated, Any
from collections import defaultdict

import trf
from litestar import post, get, delete, patch
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import HTMXTemplate
from litestar.contrib.htmx.response import ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, File
from litestar.status_codes import HTTP_200_OK

from data.tie_break import PapiTieBreak, TieBreak
from pairing.bbp_pairings import BbpPairings
from common.i18n import _
from common.logger import get_logger
from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from data.util import PlayerCategory, PrintSplit, TrfType, PrintDocument
from database.sqlite.event_database import EventDatabase
from database.store import StoredTournament, StoredScreen
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.index_controller import WebContext
from web.messages import Message

logger: Logger = get_logger()


class TournamentAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        admin_event_tab: str | None,
        tournament_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ]
        | None,
    ):
        super().__init__(
            request,
            event_uniq_id=event_uniq_id,
            admin_event_tab=admin_event_tab,
            data=data,
        )
        self.admin_tournament: Tournament | None = None
        if self.error:
            return
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
            'admin_tournament': self.admin_tournament,
        }


class TournamentAdminController(BaseEventAdminController):
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
                errors['uniq_id'] = _('Character [{char}] is not allowed.').format(
                    char='/'
                )
            else:
                match action:
                    case 'create' | 'clone':
                        if uniq_id in web_context.admin_event.tournaments_by_uniq_id:
                            errors['uniq_id'] = _(
                                'Tournament [{uniq_id}] already exists.'
                            ).format(uniq_id=uniq_id)
                    case 'update':
                        if (
                            uniq_id != web_context.admin_tournament.uniq_id
                            and uniq_id
                            in web_context.admin_event.tournaments_by_uniq_id
                        ):
                            errors['uniq_id'] = _(
                                'Tournament [{uniq_id}] already exists.'
                            ).format(uniq_id=uniq_id)
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
        chessevent_user_id: str | None = None
        chessevent_password: str | None = None
        chessevent_event_id: str | None = None
        chessevent_tournament_name: str | None = None
        record_illegal_moves: int | None = None
        rules: str | None = None
        first_board_number: int | None = None
        paired_bye_result: int | None = None
        max_byes: int | None = None
        last_rounds_no_byes: int | None = None
        tie_breaks: list[TieBreak] | None = None
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
                        'The password of the tournament on the FFE website is made of 10 uppercase letters.'
                    )
                time_control_initial_time = WebContext.form_data_to_int(
                    data, 'time_control_initial_time'
                )
                time_control_increment = WebContext.form_data_to_int(
                    data, 'time_control_increment'
                )
                time_control_handicap_penalty_value = WebContext.form_data_to_int(
                    data, 'time_control_handicap_penalty_value'
                )
                time_control_handicap_penalty_step = WebContext.form_data_to_int(
                    data, 'time_control_handicap_penalty_step'
                )
                time_control_handicap_min_time = WebContext.form_data_to_int(
                    data, 'time_control_handicap_min_time'
                )
                chessevent_user_id = WebContext.form_data_to_str(
                    data, 'chessevent_user_id'
                )
                chessevent_password = WebContext.form_data_to_str(
                    data, 'chessevent_password'
                )
                chessevent_event_id = WebContext.form_data_to_str(
                    data, 'chessevent_event_id'
                )
                chessevent_tournament_name = WebContext.form_data_to_str(
                    data, 'chessevent_tournament_name'
                )
                record_illegal_moves = (
                    cls._admin_validate_record_illegal_moves_update_data(data, errors)
                )
                rules = cls._admin_validate_rules_update_data(data, errors)
                first_board_number = WebContext.form_data_to_int(
                    data, 'first_board_number'
                )
                paired_bye_result = WebContext.form_data_to_int(
                    data, 'paired_bye_result'
                )
                max_byes = WebContext.form_data_to_int(
                    data, 'max_byes'
                )
                last_rounds_no_byes = WebContext.form_data_to_int(
                    data, 'last_rounds_no_byes'
                )
            case 'delete':
                pass
            case _:
                raise ValueError(f'action=[{action}]')

        if action == 'update':
            tie_breaks = []
            papi_tie_breaks: list[PapiTieBreak] = []
            for index in range(1, 4):
                field = f'tie_break_{index}'
                tie_break = PapiTieBreak(
                    WebContext.form_data_to_int(data, field, PapiTieBreak.NONE)
                )
                if tie_break != PapiTieBreak.NONE:
                    if tie_break in papi_tie_breaks:
                        errors[field] = _('Tie-break already in use.')
                    papi_tie_breaks.append(tie_break)
                    tie_breaks.append(
                        tie_break.to_tie_break(
                            web_context.admin_tournament.rounds
                        )
                    )

        return StoredTournament(
            id=web_context.admin_tournament.id
            if action
            not in [
                'create',
                'clone',
            ]
            else None,
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
            chessevent_user_id=chessevent_user_id,
            chessevent_password=chessevent_password,
            chessevent_event_id=chessevent_event_id,
            chessevent_tournament_name=chessevent_tournament_name,
            record_illegal_moves=record_illegal_moves,
            rules=rules,
            first_board_number=first_board_number,
            paired_bye_result=paired_bye_result,
            max_byes=max_byes,
            last_rounds_no_byes=last_rounds_no_byes,
            check_in_open=check_in_open,
            tie_breaks=tie_breaks,
            errors=errors,
        )

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
            request,
            event_uniq_id=event_uniq_id,
            admin_event_tab='tournaments',
            tournament_id=tournament_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        admin_event: Event = web_context.admin_event
        admin_tournament: Tournament = web_context.admin_tournament
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context
        )
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
                            uniq_id = admin_event.get_unused_tournament_uniq_id()
                            name = admin_event.get_unused_tournament_name()
                        case 'clone':
                            uniq_id = admin_event.get_unused_tournament_uniq_id(
                                admin_tournament.stored_tournament.uniq_id
                            )
                            name = admin_event.get_unused_tournament_name(
                                admin_tournament.stored_tournament.name
                            )
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
                    chessevent_user_id: str | None = None
                    chessevent_password: str | None = None
                    chessevent_event_id: str | None = None
                    chessevent_tournament_name: str | None = None
                    record_illegal_moves: int | None = None
                    rules: str | None = None
                    first_board_number: int | None = None
                    paired_bye_result: float | None = None
                    max_byes: int | None = None
                    last_rounds_no_byes: int | None = None
                    tie_break_1: PapiTieBreak | None = None
                    tie_break_2: PapiTieBreak | None = None
                    tie_break_3: PapiTieBreak | None = None
                    match action:
                        case 'update' | 'clone':
                            path = web_context.admin_tournament.stored_tournament.path
                            time_control_initial_time = admin_tournament.stored_tournament.time_control_initial_time
                            time_control_increment = admin_tournament.stored_tournament.time_control_increment
                            time_control_handicap_penalty_value = admin_tournament.stored_tournament.time_control_handicap_penalty_value
                            time_control_handicap_penalty_step = admin_tournament.stored_tournament.time_control_handicap_penalty_step
                            time_control_handicap_min_time = admin_tournament.stored_tournament.time_control_handicap_min_time
                            chessevent_user_id = (
                                admin_tournament.stored_tournament.chessevent_user_id
                            )
                            chessevent_password = (
                                admin_tournament.stored_tournament.chessevent_password
                            )
                            chessevent_event_id = (
                                admin_tournament.stored_tournament.chessevent_event_id
                            )
                            chessevent_tournament_name = admin_tournament.stored_tournament.chessevent_tournament_name
                            record_illegal_moves = (
                                admin_tournament.stored_tournament.record_illegal_moves
                            )
                            rules = admin_tournament.stored_tournament.rules
                            first_board_number = admin_tournament.stored_tournament.first_board_number
                            paired_bye_result = admin_tournament.stored_tournament.paired_bye_result
                            max_byes = admin_tournament.stored_tournament.max_byes
                            last_rounds_no_byes = admin_tournament.stored_tournament.last_rounds_no_byes
                        case 'create' | 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    match action:
                        case 'update':
                            filename = (
                                web_context.admin_tournament.stored_tournament.filename
                            )
                            ffe_id = (
                                web_context.admin_tournament.stored_tournament.ffe_id
                            )
                            ffe_password = web_context.admin_tournament.stored_tournament.ffe_password
                            if web_context.admin_tournament.file_exists:
                                (
                                    tie_break_1, tie_break_2, tie_break_3
                                ) = web_context.admin_tournament.papi_tie_breaks
                        case 'clone' | 'create' | 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    data = {
                        'uniq_id': WebContext.value_to_form_data(uniq_id),
                        'name': WebContext.value_to_form_data(name),
                        'path': WebContext.value_to_form_data(path),
                        'filename': WebContext.value_to_form_data(filename),
                        'time_control_initial_time': WebContext.value_to_form_data(
                            time_control_initial_time
                        ),
                        'time_control_increment': WebContext.value_to_form_data(
                            time_control_increment
                        ),
                        'time_control_handicap_penalty_value': WebContext.value_to_form_data(
                            time_control_handicap_penalty_value
                        ),
                        'time_control_handicap_penalty_step': WebContext.value_to_form_data(
                            time_control_handicap_penalty_step
                        ),
                        'time_control_handicap_min_time': WebContext.value_to_form_data(
                            time_control_handicap_min_time
                        ),
                        'chessevent_user_id': WebContext.value_to_form_data(
                            chessevent_user_id
                        ),
                        'chessevent_password': WebContext.value_to_form_data(
                            chessevent_password
                        ),
                        'chessevent_event_id': WebContext.value_to_form_data(
                            chessevent_event_id
                        ),
                        'chessevent_tournament_name': WebContext.value_to_form_data(
                            chessevent_tournament_name
                        ),
                        'record_illegal_moves': WebContext.value_to_form_data(
                            record_illegal_moves
                        ),
                        'rules': WebContext.value_to_form_data(rules),
                        'first_board_number': WebContext.value_to_form_data(first_board_number),
                        'paired_bye_result': WebContext.value_to_form_data(paired_bye_result),
                        'max_byes': WebContext.value_to_form_data(max_byes),
                        'last_rounds_no_byes': WebContext.value_to_form_data(last_rounds_no_byes),
                        'ffe_id': WebContext.value_to_form_data(ffe_id),
                        'ffe_password': WebContext.value_to_form_data(ffe_password),
                        'tie_break_1': WebContext.value_to_form_data(tie_break_1),
                        'tie_break_2': WebContext.value_to_form_data(tie_break_2),
                        'tie_break_3': WebContext.value_to_form_data(tie_break_3),
                    }
                    stored_tournament: StoredTournament = (
                        cls._admin_validate_tournament_update_data(
                            action, web_context, data
                        )
                    )
                    errors = stored_tournament.errors
                if errors is None:
                    errors = {}
                template_context |= {
                    'record_illegal_moves_options': cls._get_record_illegal_moves_options(
                        admin_event.record_illegal_moves
                    ),
                    'paired_bye_result_options': cls._get_paired_bye_result_options(),
                    'tie_break_options': cls._get_tie_break_options(),
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
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_tournaments_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='tournament',
            action='create',
            tournament_id=None,
        )

    @get(
        path='/admin/tournament-modal/{action:str}/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-modal',
        cache=1,
    )
    async def htmx_admin_tournament_modal(
        self,
        request: HTMXRequest,
        action: str,
        event_uniq_id: str,
        tournament_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_tournaments_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='tournament',
            action=action,
            tournament_id=tournament_id,
        )

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
        context = TournamentAdminWebContext(
            request, event_uniq_id, None, tournament_id, None
        )
        tournament = context.admin_tournament
        temp_file = NamedTemporaryFile(delete=False, mode='w', suffix='.trf')
        with temp_file as file:
            trf.dump(file, tournament.to_trf(usage))
        return File(
            path=temp_file.name, filename=f'{tournament.name}.{usage.file_extension}'
        )

    @post(
        path='/admin/tournament-generate-pairings/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-generate-pairings',
    )
    async def admin_tournament_generate_pairings(
        self, request: HTMXRequest, event_uniq_id: str, tournament_id: int
    ) -> Template | ClientRedirect:
        context = TournamentAdminWebContext(
            request, event_uniq_id, None, tournament_id, None
        )
        tournament = context.admin_tournament
        BbpPairings().generate_pairings(tournament)
        tournament.read_papi(True)
        return self._admin_event_tournaments_render(request, event_uniq_id)

    def _admin_tournament_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        action: str,
        event_uniq_id: str,
        tournament_id: int | None,
    ) -> Template | ClientRedirect:
        match action:
            case 'update' | 'delete' | 'clone' | 'create':
                web_context: TournamentAdminWebContext = TournamentAdminWebContext(
                    request,
                    event_uniq_id=event_uniq_id,
                    admin_event_tab='tournaments',
                    tournament_id=tournament_id,
                    data=data,
                )
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        stored_tournament: StoredTournament = (
            self._admin_validate_tournament_update_data(action, web_context, data)
        )
        if stored_tournament.errors:
            return self._admin_event_tournaments_render(
                request,
                event_uniq_id=event_uniq_id,
                modal='tournament',
                action=action,
                tournament_id=tournament_id,
                data=data,
                errors=stored_tournament.errors,
            )
        event_loader: EventLoader = EventLoader.get(request=request)
        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
            match action:
                case 'create' | 'clone':
                    stored_tournament = event_database.add_stored_tournament(
                        stored_tournament
                    )
                    if 'add_screens' in data:
                        for type_, menu, name in [
                            (
                                'input',
                                '@input',
                                _('Results entry'),
                            ),
                            (
                                'boards',
                                '@boards',
                                _('Pairings by board'),
                            ),
                            (
                                'players',
                                '@players',
                                _('Pairings by player'),
                            ),
                        ]:
                            stored_screen: StoredScreen = event_database.add_stored_screen(
                                StoredScreen(
                                    id=None,
                                    uniq_id=web_context.admin_event.get_unused_screen_uniq_id(
                                        base_uniq_id=f'{stored_tournament.uniq_id}-{type_}'
                                    ),
                                    type=type_,
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
                                )
                            )
                            event_database.add_stored_screen_set(
                                stored_screen.id, stored_tournament.id
                            )
                    event_database.commit()
                    if 'add_screens' in data:
                        Message.success(
                            request,
                            _(
                                'Tournament [{tournament_uniq_id}] has been created and default screens have been '
                                'added.'
                            ).format(tournament_uniq_id=stored_tournament.uniq_id),
                        )
                    else:
                        Message.success(
                            request,
                            _(
                                'Tournament [{tournament_uniq_id}] has been created.'
                            ).format(tournament_uniq_id=stored_tournament.uniq_id),
                        )
                    event_loader.clear_cache(event_uniq_id)
                    return self._admin_event_tournaments_render(
                        request, event_uniq_id=event_uniq_id
                    )
                case 'update':
                    stored_tournament = event_database.update_stored_tournament(
                        stored_tournament
                    )
                    Tournament(
                        web_context.admin_event, stored_tournament
                    ).update_papi_database_from_stored_tournament()
                    event_database.commit()
                    Message.success(
                        request,
                        _('Tournament [{tournament_uniq_id}] has been updated.').format(
                            tournament_uniq_id=stored_tournament.uniq_id
                        ),
                    )
                    event_loader.clear_cache(event_uniq_id)
                    return self._admin_event_tournaments_render(
                        request, event_uniq_id=event_uniq_id
                    )
                case 'delete':
                    event_database.delete_stored_tournament(
                        web_context.admin_tournament.id
                    )
                    event_database.commit()
                    Message.success(
                        request,
                        _('Tournament [{tournament_uniq_id}] has been deleted.').format(
                            tournament_uniq_id=web_context.admin_tournament.uniq_id
                        ),
                    )
                    event_loader.clear_cache(event_uniq_id)
                    return self._admin_event_tournaments_render(
                        request, event_uniq_id=event_uniq_id
                    )
                case _:
                    raise ValueError(f'action=[{action}]')

    @post(
        path='/admin/tournament-create/{event_uniq_id:str}',
        name='admin-tournament-create',
    )
    async def htmx_admin_tournament_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_tournament_update(
            request,
            event_uniq_id=event_uniq_id,
            action='create',
            tournament_id=None,
            data=data,
        )

    @patch(
        path='/admin/tournament-update/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-update',
    )
    async def htmx_admin_tournament_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        tournament_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_tournament_update(
            request,
            event_uniq_id=event_uniq_id,
            action='update',
            tournament_id=tournament_id,
            data=data,
        )

    @delete(
        path='/admin/tournament-delete/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_tournament_delete(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        tournament_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_tournament_update(
            request,
            event_uniq_id=event_uniq_id,
            action='delete',
            tournament_id=tournament_id,
            data=data,
        )

    @get(
        path='/admin/player-print-view/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-player-print-view',
    )
    async def htmx_tournament_player_print_view(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        split: str | None = None,
        document: str | None = None,
        round: int | None = None,
    ) -> Template | ClientRedirect:
        web_context: TournamentAdminWebContext = TournamentAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            admin_event_tab='tournaments',
            tournament_id=tournament_id,
            data=None,
        )
        if web_context.error:
            return web_context.error
        
        admin_tournament: Tournament = web_context.admin_tournament
        template_context: dict[str, Any] = (
            self._get_admin_event_render_context(web_context)
        )
        print_document = (
            PrintDocument(document) if document else PrintDocument.PLAYER_LIST
        )
        if print_document.is_ranking:
            round = (
                round or
                admin_tournament.max_ranking_round or
                admin_tournament.rounds
            )
            admin_tournament.set_for_ranking(round)
            ordered_players = admin_tournament.players_by_rank.values()
        else:
            ordered_players = admin_tournament.players_by_name_with_unpaired

        players_in_tournament = [
            player for player in ordered_players
            if player.tournament.id == tournament_id
        ]
        split_by = PrintSplit(split) if split else PrintSplit.NO_SPLIT
        if split_by == PrintSplit.NO_SPLIT:
            split_players = {"": players_in_tournament}
        else:
            split_functions = {
                PrintSplit.CATEGORY: lambda p: p.category.short_name,
                PrintSplit.CLUB: lambda p: p.club_tuple.club,
                PrintSplit.LEAGUE: lambda p: p.league_tuple.league,
                PrintSplit.FEDERATION: lambda p: p.federation_tuple.federation,
            }

            if split_by == PrintSplit.CATEGORY:
                split_players = {
                    category.short_name: [] for category in PlayerCategory
                }
            else:
                split_players = defaultdict(list)

            # Split players by group
            for player in players_in_tournament:
                split_players[split_functions[split_by](player)].append(player)

            if split_by == PrintSplit.CATEGORY:
                # Filter out empty categories
                split_players = {
                    key: split_players[key] for key in split_players.keys()
                    if len(split_players[key]) > 0
                }
            else:
                # Sort by key
                split_players = {
                    key: split_players[key]
                    for key in sorted(split_players.keys())
                }

        template_context |= {
            'tournament': admin_tournament,
            'players': split_players,
            'title': print_document.to_title(round),
            'rank_players': print_document.is_ranking,
            'tournament_summary': (
                print_document == PrintDocument.TOURNAMENT_SUMMARY
            ),
            'max_round': round,
        }
        return HTMXTemplate(
            template_name='admin/print/players.html', context=template_context
        )
