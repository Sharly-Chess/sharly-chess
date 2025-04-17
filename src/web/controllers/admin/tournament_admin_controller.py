import time
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated, Any
import urllib.parse

from litestar import post, get, delete, patch
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import HTMXTemplate
from litestar.contrib.htmx.response import ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, File
from litestar.status_codes import HTTP_200_OK

from common.i18n import _
from common.papi_web_config import PapiWebConfig
from data.event import Event
from data.input_output import (
    PlayerUpdaterManager,
    TournamentExporter,
    TournamentExporterManager,
)
from data.loader import EventLoader
from data.print_documents import PrintDocumentManager
from data.print_documents.options import PrintOption
from data.tie_breaks import TieBreak, TieBreakManager, PapiTieBreakManager
from data.tournament import Tournament
from utils.enum import TournamentRating
from database.access.papi.papi_database import PapiDatabase
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTournament, StoredScreen
from plugins.hookspec import ExtraColumn
from plugins.manager import plugin_manager
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.messages import Message
from web.session import SessionHandler


class TournamentAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
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
            data=data,
        )
        assert self.admin_event is not None

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
        assert web_context.admin_event is not None
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        uniq_id: str | None = WebContext.form_data_to_str(data, 'uniq_id')
        check_in_open: bool = False
        tie_breaks: list[dict] | None = None
        rounds: int | None = None
        rating: int | None = None
        start: float | None = None
        stop: float | None = None
        if action == 'delete':
            if web_context.admin_tournament is None:
                raise RuntimeError('admin_tournament not defined')
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
                        tournament = web_context.admin_tournament
                        assert tournament is not None
                        if (
                            uniq_id != tournament.uniq_id
                            and uniq_id
                            in web_context.admin_event.tournaments_by_uniq_id
                        ):
                            errors['uniq_id'] = _(
                                'Tournament [{uniq_id}] already exists.'
                            ).format(uniq_id=uniq_id)
                        check_in_open = tournament.check_in_open

                    case _:
                        raise ValueError(f'action=[{action}]')
                rounds = WebContext.form_data_to_int(data, field := 'rounds') or 1
                if rounds < 1:
                    errors[field] = _('A positive integer is expected.')
                elif action == 'update':
                    tournament = web_context.admin_tournament
                    assert tournament is not None
                    if rounds and rounds < tournament.current_round:
                        errors['rounds'] = _(
                            'Impossible to set a round number '
                            'lower than current round #{round}.'
                        ).format(round=tournament.current_round)
                rating = (
                    WebContext.form_data_to_int(data, field := 'rating')
                    or TournamentRating.STANDARD.value
                )
                try:
                    TournamentRating(rating)
                except ValueError:
                    errors[field] = f'Unknown rating [{rating}]'
                event = web_context.admin_event
                start_str = WebContext.form_data_to_str(data, field := 'start')
                if start_str:
                    start = time.mktime(
                        datetime.strptime(start_str, '%Y-%m-%dT%H:%M').timetuple()
                    )
                    if not event.start <= start <= event.stop:
                        errors[field] = _(
                            'Time outside of event time range ({start} - {stop}).'
                        ).format(
                            start=event.formatted_start_date_time,
                            stop=event.formatted_stop_date_time,
                        )
                stop_str = WebContext.form_data_to_str(data, field := 'stop')
                if stop_str:
                    stop = time.mktime(
                        datetime.strptime(stop_str, '%Y-%m-%dT%H:%M').timetuple()
                    )
                    if not event.start <= stop <= event.stop:
                        errors[field] = _(
                            'Time outside of event time range ({start} - {stop}).'
                        ).format(
                            start=event.formatted_start_date_time,
                            stop=event.formatted_stop_date_time,
                        )
                    elif start and stop < start:
                        errors[field] = _('End time needs to be after start time.')

                tie_breaks = []
                tie_break_type_by_id: dict[str, type[TieBreak]] = (
                    TieBreakManager.type_by_id()
                )
                used_tie_break_ids: list[str] = []
                for index in range(1, 4):
                    field = f'tie_break_{index}'
                    tie_break_id = WebContext.form_data_to_str(data, field)
                    if not tie_break_id:
                        continue
                    if tie_break_id in used_tie_break_ids:
                        errors[field] = _('Tie-break already in use.')
                        break
                    used_tie_break_ids.append(tie_break_id)
                    if tie_break_type := (tie_break_type_by_id.get(tie_break_id, None)):
                        tie_breaks.append(tie_break_type().to_dict())

                create_file = WebContext.form_data_to_bool(data, 'create_file')
                file_path = cls._extract_papi_file_path(data, web_context.admin_event)
                if create_file and file_path.exists():
                    errors['create_file'] = _('File already exists.')

        path: str | None = None
        filename: str | None = None
        time_control_initial_time: int | None = None
        time_control_increment: int | None = None
        time_control_handicap_penalty_value: int | None = None
        time_control_handicap_penalty_step: int | None = None
        time_control_handicap_min_time: int | None = None
        record_illegal_moves: int | None = None
        rules: str | None = None
        first_board_number: int | None = None
        paired_bye_result: int | None = None
        max_byes: int | None = None
        last_rounds_no_byes: int | None = None
        location: str | None = None
        match action:
            case 'create' | 'update' | 'clone':
                name = WebContext.form_data_to_str(data, 'name') or ''
                if not name:
                    errors['name'] = _('Please enter the tournament name.')
                path = WebContext.form_data_to_str(data, 'path')
                filename = WebContext.form_data_to_str(data, 'filename')
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
                max_byes = WebContext.form_data_to_int(data, 'max_byes')
                last_rounds_no_byes = WebContext.form_data_to_int(
                    data, 'last_rounds_no_byes'
                )
                location = WebContext.form_data_to_str(data, 'location')
            case 'delete':
                if web_context.admin_tournament is None:
                    raise RuntimeError(
                        f'{web_context.admin_tournament=} for [{action=}'
                    )
                uniq_id = web_context.admin_tournament.uniq_id
                name = web_context.admin_tournament.name
            case _:
                raise ValueError(f'action=[{action}]')

        # Have plugins validate their fields and return private plugin data
        per_plugin_tournament_data = (
            plugin_manager.hook.get_validated_tournament_form_fields(
                action=action,
                tournament=web_context.admin_tournament,
                data=data,
                errors=errors,
            )
        )
        plugin_data = {
            key: value
            for data in per_plugin_tournament_data
            for key, value in data.items()
        }

        assert uniq_id is not None

        return StoredTournament(
            id=web_context.admin_tournament.id
            if web_context.admin_tournament
            and action
            not in [
                'create',
                'clone',
            ]
            else None,
            uniq_id=uniq_id,
            name=name,
            path=path,
            filename=filename,
            time_control_initial_time=time_control_initial_time,
            time_control_increment=time_control_increment,
            time_control_handicap_penalty_value=time_control_handicap_penalty_value,
            time_control_handicap_penalty_step=time_control_handicap_penalty_step,
            time_control_handicap_min_time=time_control_handicap_min_time,
            record_illegal_moves=record_illegal_moves,
            rules=rules,
            first_board_number=first_board_number,
            paired_bye_result=paired_bye_result,
            max_byes=max_byes,
            last_rounds_no_byes=last_rounds_no_byes,
            check_in_open=check_in_open,
            tie_breaks=tie_breaks,
            location=location,
            start=start,
            stop=stop,
            rounds=rounds or 1,
            rating=rating or TournamentRating.STANDARD.value,
            errors=errors,
            plugin_data=plugin_data,
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
            tournament_id=tournament_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        admin_event: Event = web_context.admin_event
        admin_tournament: Tournament | None = web_context.admin_tournament
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context
        )

        tournament_card_blocks_and_data = (
            plugin_manager.hook.get_tournament_card_block_template_and_data()
        )
        tournament_card_blocks = [
            block_template for (block_template, data) in tournament_card_blocks_and_data
        ]
        tournament_card_block_data = {
            key: value
            for (block_template, data) in tournament_card_blocks_and_data
            for key, value in data.items()
        }
        tournament_exporters: list[TournamentExporter] = (
            TournamentExporterManager.objects()
        )
        template_context |= {
            'admin_event_tab': 'admin-event-tournaments-tab',
            'paired_bye_result_options': cls._get_paired_bye_result_options(),
            'tournament_card_blocks': tournament_card_blocks,
            'tournament_exporters': tournament_exporters,
            'admin_tournaments_show_details': (
                SessionHandler.get_session_admin_tournaments_show_details(
                    web_context.request
                )
            ),
            'player_updater_options': PlayerUpdaterManager.options(),
        } | tournament_card_block_data

        match modal:
            case None:
                pass
            case 'tournament':
                if data is None:
                    uniq_id: str | None = None
                    name: str | None = None
                    match action:
                        case 'update':
                            assert admin_tournament is not None
                            uniq_id = admin_tournament.stored_tournament.uniq_id
                            name = admin_tournament.stored_tournament.name
                        case 'create':
                            uniq_id = admin_event.get_unused_tournament_uniq_id()
                            name = admin_event.get_unused_tournament_name()
                        case 'clone':
                            assert admin_tournament is not None
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
                    time_control_initial_time: int | None = None
                    time_control_increment: int | None = None
                    time_control_handicap_penalty_value: int | None = None
                    time_control_handicap_penalty_step: int | None = None
                    time_control_handicap_min_time: int | None = None
                    record_illegal_moves: int | None = None
                    rules: str | None = None
                    first_board_number: int | None = None
                    paired_bye_result: float | None = None
                    max_byes: int | None = None
                    last_rounds_no_byes: int | None = None
                    tie_break_1: str | None = None
                    tie_break_2: str | None = None
                    tie_break_3: str | None = None
                    location: str | None = None
                    start: float | None = None
                    stop: float | None = None
                    rounds: int | None = None
                    rating: TournamentRating | None = None
                    match action:
                        case 'update' | 'clone':
                            assert admin_tournament is not None
                            assert admin_tournament.stored_tournament is not None
                            stored_tournament = admin_tournament.stored_tournament
                            path = stored_tournament.path
                            time_control_initial_time = (
                                stored_tournament.time_control_initial_time
                            )
                            time_control_increment = (
                                stored_tournament.time_control_increment
                            )
                            time_control_handicap_penalty_value = (
                                stored_tournament.time_control_handicap_penalty_value
                            )
                            time_control_handicap_penalty_step = (
                                stored_tournament.time_control_handicap_penalty_step
                            )
                            time_control_handicap_min_time = (
                                stored_tournament.time_control_handicap_min_time
                            )
                            record_illegal_moves = (
                                stored_tournament.record_illegal_moves
                            )
                            rules = stored_tournament.rules
                            first_board_number = stored_tournament.first_board_number
                            paired_bye_result = stored_tournament.paired_bye_result
                            max_byes = stored_tournament.max_byes
                            last_rounds_no_byes = stored_tournament.last_rounds_no_byes
                            location = stored_tournament.location
                            start = stored_tournament.start
                            stop = stored_tournament.stop
                            rating = admin_tournament.rating
                            rounds = admin_tournament.rounds or 1
                        case 'create':
                            rounds = 1
                            rating = TournamentRating.STANDARD
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    match action:
                        case 'update':
                            assert admin_tournament is not None
                            assert admin_tournament.stored_tournament is not None
                            filename = admin_tournament.stored_tournament.filename
                            if admin_tournament.file_exists:
                                tie_breaks = admin_tournament.tie_breaks
                                tie_break_1, tie_break_2, tie_break_3 = (
                                    tie_breaks.pop(0).id if tie_breaks else None
                                    for __ in range(3)
                                )
                        case 'clone' | 'create' | 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')

                    per_plugin_form_data = plugin_manager.hook.get_tournament_form_data(
                        tournament=web_context.admin_tournament
                    )
                    plugin_form_data = {
                        key: value
                        for data in per_plugin_form_data
                        for key, value in data.items()
                    }
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
                        'record_illegal_moves': WebContext.value_to_form_data(
                            record_illegal_moves
                        ),
                        'rules': WebContext.value_to_form_data(rules),
                        'first_board_number': WebContext.value_to_form_data(
                            first_board_number
                        ),
                        'paired_bye_result': WebContext.value_to_form_data(
                            paired_bye_result
                        ),
                        'max_byes': WebContext.value_to_form_data(max_byes),
                        'last_rounds_no_byes': WebContext.value_to_form_data(
                            last_rounds_no_byes
                        ),
                        'tie_break_1': WebContext.value_to_form_data(tie_break_1),
                        'tie_break_2': WebContext.value_to_form_data(tie_break_2),
                        'tie_break_3': WebContext.value_to_form_data(tie_break_3),
                        'location': WebContext.value_to_form_data(location),
                        'start': WebContext.value_to_datetime_form_data(start),
                        'stop': WebContext.value_to_datetime_form_data(stop),
                        'rounds': WebContext.value_to_form_data(rounds),
                        'rating': WebContext.value_to_form_data(
                            rating.value if rating else None
                        ),
                    } | plugin_form_data
                    stored_tournament: StoredTournament = (
                        cls._admin_validate_tournament_update_data(
                            action, web_context, data
                        )
                    )
                    errors = stored_tournament.errors
                if errors is None:
                    errors = {}

                plugin_form_fields_templates = (
                    plugin_manager.hook.get_tournament_form_fields_template() or []
                )
                template_context |= {
                    'record_illegal_moves_options': cls._get_record_illegal_moves_options(
                        admin_event.record_illegal_moves
                    ),
                    'paired_bye_result_options': cls._get_paired_bye_result_options(),
                    'tie_break_options': {'': _('None')}
                    | PapiTieBreakManager.options(),
                    'rating_options': cls._get_rating_options(),
                    'plugin_form_fields_templates': plugin_form_fields_templates,
                    'file_exists': cls._extract_papi_file_path(
                        data, admin_event
                    ).exists(),
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case _:
                raise ValueError(f'modal=[{modal}]')
        return cls._admin_event_render(template_context)

    @get(
        path='/admin/event/{event_uniq_id:str}/tournaments',
        name='admin-event-tournaments-tab',
        cache=1,
    )
    async def htmx_admin_event_tournaments_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        admin_tournaments_show_details: bool | None,
    ) -> Template | ClientRedirect:
        if admin_tournaments_show_details is not None:
            SessionHandler.set_session_admin_tournaments_show_details(
                request, admin_tournaments_show_details
            )
        return self._admin_event_tournaments_render(
            request,
            event_uniq_id=event_uniq_id,
        )

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
        path='/admin/tournament-export/{event_uniq_id:str}/{tournament_id:int}/{exporter_id:str}',
        name='admin-tournament-export',
    )
    async def admin_tournament_export(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        exporter_id: str,
    ) -> File:
        context = TournamentAdminWebContext(request, event_uniq_id, tournament_id, None)
        tournament = context.admin_tournament
        if tournament is None:
            raise RuntimeError('tournament not defined')
        exporter = TournamentExporterManager.get_object(exporter_id)
        temp_file = NamedTemporaryFile(
            delete=False,
            mode='wb' if exporter.is_binary_file else 'w',
            encoding=exporter.file_encoding,
        )
        with temp_file:
            exporter.dump_to_file(temp_file, tournament)
        return File(
            path=temp_file.name,
            filename=f'{exporter.file_name(tournament)}.{exporter.file_extension}',
        )

    @post(
        path='/admin/tournament-file-status/{event_uniq_id:str}',
        name='admin-tournament-file-status',
    )
    async def admin_tournament_file_status(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        web_context = TournamentAdminWebContext(request, event_uniq_id, None, data)
        assert web_context.admin_event is not None
        template_context: dict[str, Any] = self._get_admin_event_render_context(
            web_context
        )
        return HTMXTemplate(
            template_name='admin/tournaments/file_status.html',
            context=template_context
            | {
                'file_exists': self._extract_papi_file_path(
                    data, web_context.admin_event
                ).exists(),
            },
        )

    @staticmethod
    def _extract_papi_file_path(data: dict[str, str], event: Event) -> Path:
        dir_path = Path(WebContext.form_data_to_str(data, 'path') or event.path)
        file_name = WebContext.form_data_to_str(
            data, 'filename'
        ) or WebContext.form_data_to_str(data, 'uniq_id', '')
        return dir_path / f'{file_name}.{PapiWebConfig.papi_ext}'

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
                    tournament_id=tournament_id,
                    data=data,
                )
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
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
        if WebContext.form_data_to_bool(data, 'create_file'):
            file_path = self._extract_papi_file_path(data, web_context.admin_event)
            PapiDatabase(file_path).create_empty()

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
                            (
                                'ranking',
                                '@ranking',
                                _('Ranking'),
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
                                    font_size=None,
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
                            assert stored_screen.id is not None
                            assert stored_tournament.id is not None
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
                    assert web_context.admin_tournament is not None
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
        path='/admin/tournament-print-view/{event_uniq_id:str}/{tournament_id:int}/{document: str}',
        name='admin-tournament-print-view',
    )
    async def htmx_tournament_print_view(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        document: str,
        options: str | None = None,
    ) -> Template | ClientRedirect:
        web_context: TournamentAdminWebContext = TournamentAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            data=None,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_tournament is None:
            raise RuntimeError('admin_tournament not defined')
        admin_tournament: Tournament = web_context.admin_tournament
        template_context: dict[str, Any] = self._get_admin_event_render_context(
            web_context
        )
        document_type = PrintDocumentManager.get_type(document)
        option_data: dict[str, str] = {}
        if options:
            for option in urllib.parse.unquote(options).split('|'):
                key, value = option.split('=')
                option_data[key] = value
        print_options: list[PrintOption] = []
        for print_option in document_type.default_options():
            value = (
                WebContext.form_data_to_value(
                    option_data,
                    print_option.id,
                    print_option.type,  # type: ignore
                    print_option.default_value,
                )
                or ''
            )
            print_options.append(type(print_option)(value))
        print_document = document_type(print_options, admin_tournament)

        per_plugin_columns = plugin_manager.hook.get_extra_print_view_columns(
            document=print_document
        )
        extra_columns: dict[str, list[ExtraColumn]] = {}
        for plugin_columns in per_plugin_columns:
            for extra_column in plugin_columns:
                c = extra_columns.setdefault(extra_column.at, [])
                c.append(extra_column)
        per_plugin_css: list[str] = plugin_manager.hook.get_extra_print_view_css(
            document=print_document
        )
        extra_css: str = '\n'.join(per_plugin_css)

        template_context |= {
            'document': print_document,
            'extra_columns': extra_columns,
            'extra_css': extra_css,
        } | print_document.template_context
        return HTMXTemplate(
            template_name=print_document.template_name, context=template_context
        )
