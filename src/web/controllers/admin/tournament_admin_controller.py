import random
import time
from datetime import datetime
from tempfile import NamedTemporaryFile
from typing import Annotated, Any

from litestar import post, get, patch, delete
from litestar.exceptions import NotFoundException, ClientException
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, File
from litestar.status_codes import HTTP_200_OK

from common.exception import SharlyChessException, OptionError, ImporterError
from common.logger import get_logger
from common.i18n import _
from data.access_levels.actions import AuthAction
from data.board import Board, PlayerRatingType
from data.event import Event
from data.input_output import (
    DataSourceManager,
    TournamentExporter,
    TournamentExporterManager,
    TournamentImporterManager,
)
from data.input_output.tournament_importer_options import TournamentImporterOption
from data.input_output.tournament_importers import TournamentImporter
from data.pairings import PairingSystem, PairingSystemManager
from data.pairings.systems import SwissPairingSystem
from data.player import Player
from data.criteria.managers import (
    PlayerFilter,
    PlayerFilterManager,
    PlayerFilterOptionManager,
)
from data.tie_breaks import TieBreak, TieBreakManager
from data.tournament import Tournament
from data.tournament_criterion import TournamentCriterion
from utils import StaticUtils
from utils.enum import FormAction, Result, TournamentRating
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredTournament,
    StoredScreen,
    StoredTournamentCriterion,
)
from plugins.manager import plugin_manager
from utils.time_control import parse_time_control_trf25
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.guards import EventGuard, ActionGuard
from web.messages import Message
from web.session import SessionHandler


logger = get_logger()


class TournamentAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        tournament_id: int | None = None,
        criterion_id: int | None = None,
        reload_event: bool = False,
    ):
        super().__init__(request, reload_event)
        assert self.admin_event is not None

        self.admin_tournament: Tournament | None = None
        if tournament_id:
            try:
                self.admin_tournament = self.admin_event.tournaments_by_id[
                    tournament_id
                ]
            except KeyError:
                raise NotFoundException(f'Tournament [{tournament_id}] not found.')

        self.admin_tournament_criterion: TournamentCriterion | None = None
        if criterion_id:
            assert self.admin_tournament is not None
            if criterion_id not in self.admin_tournament.criteria_by_id:
                raise NotFoundException(
                    f'Unknown criterion ID [{criterion_id}] for tournament [{self.admin_tournament.name}].'
                )
            self.admin_tournament_criterion = self.admin_tournament.criteria_by_id[
                criterion_id
            ]

    def get_admin_tournament(self) -> Tournament:
        assert self.admin_tournament is not None
        return self.admin_tournament

    def get_admin_tournament_criterion(self) -> TournamentCriterion:
        assert self.admin_tournament_criterion is not None
        return self.admin_tournament_criterion

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_tournament': self.admin_tournament,
            'admin_tournament_criterion': self.admin_tournament_criterion,
        }


class TournamentAdminController(BaseEventAdminController):
    guards = [
        EventGuard(),
        ActionGuard(AuthAction.VIEW_TOURNAMENTS_TAB),
    ]

    @classmethod
    def _admin_event_tournaments_render(
        cls,
        web_context: TournamentAdminWebContext,
        template_context: dict[str, Any] | None = None,
    ) -> Template:
        event = web_context.get_admin_event()
        tournament_form_fields_templates_and_data = plugin_manager.hook_for_event(
            event, 'get_tournament_card_block_template_and_data'
        )()
        tournament_card_blocks = [
            block_template
            for (block_template, data) in tournament_form_fields_templates_and_data
        ]
        tournament_card_block_data = {
            key: value
            for (block_template, data) in tournament_form_fields_templates_and_data
            for key, value in data.items()
        }
        tournament_card_action_menu_items_templates = plugin_manager.hook_for_event(
            event, 'get_tournament_card_action_menu_items_template'
        )()
        tournament_tab_action_menu_items_templates = plugin_manager.hook_for_event(
            event, 'get_tournament_tab_action_menu_items_template'
        )()
        tournament_importers: list[TournamentImporter] = TournamentImporterManager(
            event
        ).objects()
        tournament_exporters: list[TournamentExporter] = TournamentExporterManager(
            event
        ).objects()
        template_context = (
            web_context.template_context
            | {
                'admin_event_tab': 'admin-event-tournaments-tab',
                'tournament_card_blocks': tournament_card_blocks,
                'tournament_importers': tournament_importers,
                'tournament_exporters': tournament_exporters,
                'tournament_card_action_menu_items_templates': tournament_card_action_menu_items_templates,
                'tournament_tab_action_menu_items_templates': tournament_tab_action_menu_items_templates,
                'admin_tournaments_show_details': (
                    SessionHandler.get_session_admin_tournaments_show_details(
                        web_context.request
                    )
                ),
                'data_sources': DataSourceManager().objects(),
            }
            | tournament_card_block_data
            | (template_context or {})
        )

        return cls._admin_base_event_render(template_context)

    @get(
        path='/event/{event_uniq_id:str}/tournaments',
        name='admin-event-tournaments-tab',
    )
    async def htmx_admin_event_tournaments_tab(
        self,
        request: HTMXRequest,
        admin_tournaments_show_details: bool | None,
    ) -> Template:
        web_context = TournamentAdminWebContext(request)
        if admin_tournaments_show_details is not None:
            SessionHandler.set_session_admin_tournaments_show_details(
                request, admin_tournaments_show_details
            )

        return self._admin_event_tournaments_render(web_context)

    @classmethod
    def _prepare_tournament_modal_data(
        cls,
        action: FormAction,
        web_context: TournamentAdminWebContext,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ):
        admin_event = web_context.get_admin_event()
        pairing_systems = PairingSystemManager(admin_event).objects()
        pairing_system: PairingSystem = SwissPairingSystem()
        if data is None:
            match action:
                case 'update':
                    name = web_context.get_admin_tournament().stored_tournament.name
                case 'create':
                    name = admin_event.get_unused_tournament_name()
                case 'clone':
                    name = admin_event.get_unused_tournament_name(
                        web_context.get_admin_tournament().stored_tournament.name
                    )
                case _:
                    raise ValueError(f'action=[{action}]')
            time_control_trf25: str | None = None
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
            player_rating_type: int | None = None
            start: float | None = None
            stop: float | None = None
            rounds: int | None = None
            rating: int | None = None
            pairing_variations: dict[str, str | None] = {
                system.variation_field_id: None for system in pairing_systems
            }
            three_points_for_a_win: bool | None = None
            pab_value: int | None = None
            override_unrated_rapid_blitz: bool | None = None
            stored_plugin_data: dict[str, dict[str, Any]] = {}
            match action:
                case 'update' | 'clone':
                    admin_tournament = web_context.get_admin_tournament()
                    assert admin_tournament.stored_tournament is not None
                    stored_tournament = admin_tournament.stored_tournament
                    time_control_trf25 = stored_tournament.time_control_trf25
                    time_control_handicap_penalty_value = (
                        stored_tournament.time_control_handicap_penalty_value
                    )
                    time_control_handicap_penalty_step = (
                        stored_tournament.time_control_handicap_penalty_step
                    )
                    time_control_handicap_min_time = (
                        stored_tournament.time_control_handicap_min_time
                    )
                    record_illegal_moves = stored_tournament.record_illegal_moves
                    rules = stored_tournament.rules
                    first_board_number = stored_tournament.first_board_number
                    paired_bye_result = stored_tournament.paired_bye_result
                    max_byes = stored_tournament.max_byes
                    last_rounds_no_byes = stored_tournament.last_rounds_no_byes
                    location = stored_tournament.location
                    player_rating_type = stored_tournament.player_rating_type
                    start = stored_tournament.start
                    stop = stored_tournament.stop
                    rating = admin_tournament.rating.value
                    rounds = admin_tournament.rounds or 1
                    pairing_system = admin_tournament.pairing_system
                    pairing_variations[
                        admin_tournament.pairing_system.variation_field_id
                    ] = admin_tournament.pairing_variation.id
                    three_points_for_a_win = stored_tournament.three_points_for_a_win
                    pab_value = stored_tournament.pab_value
                    override_unrated_rapid_blitz = (
                        stored_tournament.override_unrated_rapid_blitz
                    )
                    stored_plugin_data = stored_tournament.plugin_data
                case 'create':
                    rounds = 1
                    rating = TournamentRating.STANDARD.value
                case _:
                    raise ValueError(f'action=[{action}]')
            if action in [
                'update',
                'clone',
            ]:
                assert admin_tournament is not None
                assert admin_tournament.stored_tournament is not None
                tie_breaks = admin_tournament.tie_breaks
                tie_break_1, tie_break_2, tie_break_3 = (
                    tie_breaks.pop(0).id if tie_breaks else None for __ in range(3)
                )

            plugin_form_data: dict[str, str] = {}
            for (
                plugin_id,
                plugin_data_class,
            ) in Tournament.plugin_data_class_by_plugin_id().items():
                plugin_form_data |= plugin_data_class.from_stored_value(
                    stored_plugin_data.get(plugin_id, {})
                ).to_form_data(action=action)

            data: dict[str, str] = {
                'start': WebContext.value_to_datetime_form_data(start),
                'stop': WebContext.value_to_datetime_form_data(stop),
            } | WebContext.values_dict_to_form_data(
                {
                    'name': name,
                    'time_control_trf25': time_control_trf25,
                    'time_control_handicap_penalty_value': time_control_handicap_penalty_value,
                    'time_control_handicap_penalty_step': time_control_handicap_penalty_step,
                    'time_control_handicap_min_time': time_control_handicap_min_time,
                    'record_illegal_moves': record_illegal_moves,
                    'rules': rules,
                    'first_board_number': first_board_number,
                    'paired_bye_result': paired_bye_result,
                    'max_byes': max_byes,
                    'last_rounds_no_byes': last_rounds_no_byes,
                    'tie_break_1': tie_break_1,
                    'tie_break_2': tie_break_2,
                    'tie_break_3': tie_break_3,
                    'location': location,
                    'player_rating_type': player_rating_type,
                    'rounds': rounds,
                    'rating': rating,
                    'pairing_system': pairing_system.id,
                    'three_points_for_a_win': three_points_for_a_win,
                    'pab_value': pab_value,
                    'override_unrated_rapid_blitz': override_unrated_rapid_blitz,
                }
                | {field: variation for field, variation in pairing_variations.items()}
                | plugin_form_data
            )
            stored_tournament, errors = cls._admin_get_validated_tournament_data(
                action, web_context, data
            )

        plugin_results = plugin_manager.hook_for_event(
            admin_event, 'get_tournament_form_fields_template_and_data'
        )(event=admin_event, tournament=web_context.admin_tournament)

        plugin_form_fields_templates = [template for template, __ in plugin_results]
        form_fields_templates_data = {
            key: value for __, data in plugin_results for key, value in data.items()
        }
        tie_break_options = {'': '-'} | {
            type_.static_id(): type_.static_name()
            for type_ in sorted(
                TieBreakManager(admin_event).entity_types(),
                key=lambda tie_break: tie_break.static_name(),
            )
        }

        override_unrated_rapid_blitz_options = {
            '': '',
            WebContext.value_to_form_data(True): _('Use standard ratings'),
            WebContext.value_to_form_data(False): _('Fallback to estimated ratings'),
        }

        override_unrated_rapid_blitz_options[''] = _(
            "Use Event's default - {option}"
        ).format(
            option=override_unrated_rapid_blitz_options[
                WebContext.value_to_form_data(
                    admin_event.override_unrated_rapid_blitz or False
                )
            ]
        )

        player_rating_type_options: dict[str, str] = {
            '': '',
            str(PlayerRatingType.FIDE.value): _('FIDE'),
            str(PlayerRatingType.NATIONAL.value): _(
                'National *** NAME FOR RATING TYPE NATIONAL'
            ),
        }
        player_rating_type_options[''] = _("Use Event's default - {option}").format(
            option=player_rating_type_options[str(admin_event.player_rating_type.value)]
        )

        three_points_for_a_win_options = {
            '': '',
            WebContext.value_to_form_data(True): _('Three points for a win (3-1-0)'),
            WebContext.value_to_form_data(False): _('Standard points (1-0.5-0)'),
        }
        three_points_for_a_win_options[''] = _("Use Event's default - {option}").format(
            option=three_points_for_a_win_options[
                WebContext.value_to_form_data(
                    admin_event.three_points_for_a_win or False
                )
            ]
        )

        pab_value_options = {
            '': '',
            str(Result.WIN.value): _('Win'),
            str(Result.DRAW.value): _('Draw'),
            str(Result.LOSS.value): _('Loss'),
        }
        pab_value_options[''] = _("Use Event's default - {option}").format(
            option=pab_value_options[str(admin_event.pab_value.value)]
        )

        template_context = {
            'tie_break_options': tie_break_options,
            'rating_options': cls._get_rating_options(),
            'override_unrated_rapid_blitz_options': override_unrated_rapid_blitz_options,
            'pairing_systems': pairing_systems,
            'pairing_system_options': PairingSystemManager(admin_event).options(),
            'plugin_form_fields_templates': plugin_form_fields_templates,
            'previous_tournament': (
                web_context.admin_tournament if action == 'create' else None
            ),
            'add_other_active': (
                SessionHandler.get_session_admin_tournament_add_other_active(
                    web_context.request
                )
            ),
            'admin_tournament': None
            if action == 'clone'
            else web_context.admin_tournament,
            'player_rating_type_options': player_rating_type_options,
            'pab_value_options': pab_value_options,
            'three_points_for_a_win_options': three_points_for_a_win_options,
            'modal': 'tournament',
            'action': action,
            'data': data,
            'errors': errors,
        } | form_fields_templates_data

        return template_context

    @classmethod
    def _admin_get_validated_tournament_data(
        cls,
        action: str,
        web_context: TournamentAdminWebContext,
        data: dict[str, str] | None = None,
    ) -> tuple[StoredTournament, dict[str, str]]:
        assert web_context.admin_event is not None
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        check_in_open: bool = False
        start: float | None = None
        stop: float | None = None
        rounds = WebContext.form_data_to_int(data, field := 'rounds') or 1
        tournament: Tournament | None = None
        if rounds < 1:
            errors[field] = _('A positive integer is expected.')
        elif action == 'update':
            tournament = web_context.admin_tournament
            assert tournament is not None
            if rounds < tournament.last_paired_round:
                errors['rounds'] = _(
                    'Impossible to set a round number lower '
                    'than the last round with pairings #{round}.'
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

        pairing_system = PairingSystemManager(web_context.admin_event).get_object(
            WebContext.form_data_to_str(data, 'pairing_system')
            or SwissPairingSystem.static_id()
        )
        pairing = WebContext.form_data_to_str(
            data, f'{pairing_system.id}_pairing_variation'
        )

        tie_breaks = []
        tie_break_type_by_id: dict[str, type[TieBreak]] = TieBreakManager(
            web_context.admin_event
        ).type_by_id()
        used_tie_break_ids: list[str] = []
        for index in (1, 2, 3):
            field = f'tie_break_{index}'
            tie_break_id = WebContext.form_data_to_str(data, field)
            if not tie_break_id:
                continue
            if tie_break_id in used_tie_break_ids:
                errors[field] = _('Tie-break already in use.')
                break
            used_tie_break_ids.append(tie_break_id)
            if tie_break_type := (tie_break_type_by_id.get(tie_break_id, None)):
                tie_break = tie_break_type()
                if pairing_system in tie_break.forbidden_pairing_systems:
                    errors[field] = _(
                        'Tie-break incompatible with the "{system}" pairing system.'
                    ).format(system=pairing_system.name)
                    break
                tie_breaks.append(tie_break.to_dict())

        if action == 'update':
            tournament = web_context.admin_tournament
            assert tournament is not None
            if tournament.started:
                not_updatable_values: dict[str, str] = {
                    'rating': str(tournament.rating.value),
                    tournament.pairing_system.variation_field_id: tournament.pairing_variation.id,
                    'pairing_system': tournament.pairing_system.id,
                }
                if not tournament.pairing_system.allow_rounds_update_once_started:
                    not_updatable_values |= {'rounds': str(tournament.rounds)}
                for field, expected_value in not_updatable_values.items():
                    if data.get(field, '') != expected_value:
                        errors[field] = _(
                            "This field can't be updated once the tournament has started."
                        )
        name = WebContext.form_data_to_str(data, field := 'name') or ''
        if not name:
            errors['name'] = _('This field is required.')
        else:
            used_names = list(event.tournaments_by_uniq_id.keys())
            if action == 'update':
                used_names.remove(web_context.get_admin_tournament().name)
            if name in used_names:
                errors[field] = _('This name is already used.')
        time_control_trf25 = WebContext.form_data_to_str(data, 'time_control_trf25')
        time_control_handicap_penalty_value = WebContext.form_data_to_int(
            data, 'time_control_handicap_penalty_value'
        )
        time_control_handicap_penalty_step = WebContext.form_data_to_int(
            data, 'time_control_handicap_penalty_step'
        )
        time_control_handicap_min_time = WebContext.form_data_to_int(
            data, 'time_control_handicap_min_time'
        )

        intial_time, inc = parse_time_control_trf25(time_control_trf25)
        if intial_time == 0 and time_control_handicap_penalty_value:
            errors['time_control_handicap_penalty_value'] = _(
                'Penalties require a time control with a single period.'
            )

        record_illegal_moves = cls._admin_validate_record_illegal_moves_update_data(
            data, errors
        )
        rules = cls._admin_validate_rules_update_data(data, errors)
        first_board_number = WebContext.form_data_to_int(data, 'first_board_number')
        paired_bye_result = WebContext.form_data_to_int(data, 'paired_bye_result')
        max_byes = WebContext.form_data_to_int(data, 'max_byes')
        last_rounds_no_byes = WebContext.form_data_to_int(data, 'last_rounds_no_byes')
        location = WebContext.form_data_to_str(data, 'location')
        player_rating_type = WebContext.form_data_to_int(data, 'player_rating_type')
        three_points_for_a_win = WebContext.form_data_to_bool_or_none(
            data, 'three_points_for_a_win'
        )
        override_unrated_rapid_blitz = WebContext.form_data_to_bool_or_none(
            data, 'override_unrated_rapid_blitz'
        )
        pab_value = WebContext.form_data_to_int(data, 'pab_value')

        # Validate
        plugin_manager.hook_for_event(
            web_context.get_admin_event(), 'validate_tournament_form_fields'
        )(
            action=action,
            tournament=web_context.admin_tournament,
            data=data,
            errors=errors,
        )

        plugin_data: dict[str, dict[str, Any]] = {}
        for (
            plugin_id,
            plugin_data_class,
        ) in Tournament.plugin_data_class_by_plugin_id().items():
            previous_object = None
            if tournament is not None:
                previous_object = tournament.plugin_data.get(plugin_id)

            plugin_data[plugin_id] = plugin_data_class.from_form_data(
                data, action=action, previous_object=previous_object
            ).to_stored_value()

        stored_tournament = StoredTournament(
            id=web_context.admin_tournament.id
            if web_context.admin_tournament
            and action
            not in [
                'create',
                'clone',
            ]
            else None,
            name=name,
            time_control_trf25=time_control_trf25,
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
            player_rating_type=player_rating_type,
            start=start,
            stop=stop,
            rounds=rounds or 1,
            rating=rating or TournamentRating.STANDARD.value,
            pairing=pairing or '',
            three_points_for_a_win=three_points_for_a_win,
            pab_value=pab_value,
            override_unrated_rapid_blitz=override_unrated_rapid_blitz,
            plugin_data=plugin_data,
        )
        return (stored_tournament, errors)

    @get(
        path='/tournament-modal/create/{event_uniq_id:str}',
        name='admin-tournament-create-modal',
    )
    async def htmx_admin_tournament_create_modal(
        self, request: HTMXRequest
    ) -> Template:
        web_context = TournamentAdminWebContext(request)
        template_context = self._prepare_tournament_modal_data(
            FormAction.CREATE, web_context
        )

        return self._admin_event_tournaments_render(
            web_context=web_context,
            template_context=template_context,
        )

    @get(
        path='/tournament-modal/{action:str}/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-modal',
    )
    async def htmx_admin_tournament_modal(
        self,
        request: HTMXRequest,
        action: FormAction,
        tournament_id: int | None,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id=tournament_id)
        template_context = self._prepare_tournament_modal_data(action, web_context)

        return self._admin_event_tournaments_render(
            web_context=web_context,
            template_context=template_context,
        )

    def _admin_tournament_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        action: FormAction,
        tournament_id: int | None,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id=tournament_id)
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        add_other = 'add_other' in data
        if action == FormAction.CREATE:
            SessionHandler.set_session_admin_tournament_add_other_active(
                request, add_other
            )

        stored_tournament, errors = self._admin_get_validated_tournament_data(
            action, web_context, data
        )
        if errors:
            template_context = self._prepare_tournament_modal_data(
                action, web_context, data, errors=errors
            )
            return self._admin_event_tournaments_render(
                web_context=web_context,
                template_context=template_context,
            )

        if message := plugin_manager.hook_for_event(
            web_context.admin_event, 'signal_tournament_set'
        )(event=web_context.admin_event, stored_tournament=stored_tournament):
            Message.warning(request, message)

        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
            if action == FormAction.UPDATE:
                stored_tournament = event_database.update_stored_tournament(
                    stored_tournament
                )
                success_message = _(
                    'Tournament [{tournament}] has been updated.'
                ).format(tournament=stored_tournament.name)
            else:
                stored_tournament = event_database.add_stored_tournament(
                    stored_tournament
                )
                if 'add_screens' in data:
                    timer_id: int | None = None
                    if len(web_context.admin_event.timers_by_id) == 1:
                        timer_id = list(web_context.admin_event.timers_by_id.keys())[0]
                    for type_, menu, name in [
                        (
                            'input',
                            '@input',
                            _('Check-in / Results entry ({tournament_name})').format(
                                tournament_name=stored_tournament.name
                            ),
                        ),
                        (
                            'boards',
                            '@boards',
                            _('Pairings by board ({tournament_name})').format(
                                tournament_name=stored_tournament.name
                            ),
                        ),
                        (
                            'players',
                            '@players',
                            _('Pairings by player ({tournament_name})').format(
                                tournament_name=stored_tournament.name
                            ),
                        ),
                        (
                            'ranking',
                            '@ranking',
                            _('Ranking ({tournament_name})').format(
                                tournament_name=stored_tournament.name
                            ),
                        ),
                    ]:
                        stored_screen: StoredScreen = event_database.add_stored_screen(
                            StoredScreen(
                                id=None,
                                uniq_id=web_context.admin_event.get_unused_screen_uniq_id(
                                    base_uniq_id=StaticUtils.name_to_uniq_id(
                                        f'{stored_tournament.name}-{type_}'
                                    )
                                ),
                                type=type_,
                                public=True,
                                name=name,
                                columns=1,
                                font_size=None,
                                menu_link=True,
                                menu_text=None,
                                menu=menu,
                                timer_id=timer_id,
                                input_exit_button=None,
                                players_show_unpaired=None,
                                players_show_opponent=None,
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
                    success_message = _(
                        'Tournament [{tournament}] has been created '
                        'and default screens have been added.'
                    ).format(tournament=stored_tournament.name)
                else:
                    success_message = _(
                        'Tournament [{tournament}] has been created.'
                    ).format(tournament=stored_tournament.name)

                tournament_id = stored_tournament.id

        if add_other:
            web_context = TournamentAdminWebContext(
                request, tournament_id, reload_event=True
            )
            template_context = self._prepare_tournament_modal_data(
                FormAction.CREATE, web_context
            )
            return self._admin_event_tournaments_render(
                web_context=web_context,
                template_context=template_context,
            )
        Message.success(request, success_message)

        web_context = TournamentAdminWebContext(
            request, tournament_id, reload_event=True
        )
        return self._admin_event_tournaments_render(web_context)

    @post(
        path='/tournament-create/{event_uniq_id:str}',
        name='admin-tournament-create',
        guards=[ActionGuard(AuthAction.ADD_TOURNAMENTS)],
    )
    async def htmx_admin_tournament_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        return self._admin_tournament_update(
            request,
            action=FormAction.CREATE,
            tournament_id=None,
            data=data,
        )

    @patch(
        path='/tournament-update/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-update',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_tournament_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
    ) -> Template:
        return self._admin_tournament_update(
            request,
            action=FormAction.UPDATE,
            tournament_id=tournament_id,
            data=data,
        )

    @get(
        path='/tournament-delete-modal/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-delete-modal',
    )
    async def htmx_admin_tournament_delete_modal(
        self,
        request: HTMXRequest,
        tournament_id: int | None,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        return self._admin_base_event_render(
            web_context.template_context | {'modal': 'tournament-delete'}
        )

    @delete(
        path='/tournament-delete/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-delete',
        guards=[ActionGuard(AuthAction.DELETE_TOURNAMENTS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_tournament_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        with EventDatabase(event_uniq_id, True) as database:
            database.delete_stored_tournament(tournament_id)
        Message.success(
            request,
            _('Tournament [{tournament}] has been deleted.').format(
                tournament=web_context.get_admin_tournament().name
            ),
        )

        web_context = TournamentAdminWebContext(request, reload_event=True)
        return self._admin_event_tournaments_render(web_context)

    # -------------------------------------------------------------------------
    # Tournament import/export
    # -------------------------------------------------------------------------

    @get(
        path='/tournament-export/{event_uniq_id:str}/{tournament_id:int}/{exporter_id:str}',
        name='admin-tournament-export',
    )
    async def admin_tournament_export(
        self,
        request: HTMXRequest,
        tournament_id: int,
        exporter_id: str,
    ) -> File:
        web_context = TournamentAdminWebContext(request, tournament_id)
        event = web_context.get_admin_event()
        tournament = web_context.get_admin_tournament()
        exporter = TournamentExporterManager(event).get_object(exporter_id)
        temp_file = NamedTemporaryFile(
            delete=False,
            mode='wb' if exporter.is_binary_file else 'w',
            suffix=f'.{exporter.file_extension}',
            encoding=exporter.file_encoding,
        )
        with temp_file:
            exporter.dump_to_file(temp_file, tournament)
        return File(
            path=temp_file.name,
            filename=f'{exporter.file_name(tournament)}.{exporter.file_extension}',
        )

    @staticmethod
    def _tournament_import_modal_context(
        event: Event,
        importer_id: str,
        tournament: Tournament | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        importer = TournamentImporterManager(event).get_object(importer_id)
        default_data = WebContext.values_dict_to_form_data(
            {
                option.id: option.get_default_value(tournament)
                for option in importer.default_options()
            }
        )
        context: dict[str, Any] = {
            'data': default_data | (data or {}),
            'importer': importer,
            'modal': 'tournament-import',
            'errors': errors or {},
        }
        for option in importer.default_options():
            context |= option.template_context
        return context

    @get(
        path=[
            '/tournament-import-modal/{event_uniq_id:str}/{importer_id:str}',
            '/tournament-import-modal/{event_uniq_id:str}/{tournament_id:int}/{importer_id:str}',
        ],
        name='admin-tournament-import-modal',
    )
    async def htmx_admin_tournament_import_modal(
        self,
        request: HTMXRequest,
        tournament_id: int | None,
        importer_id: str,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        event = web_context.get_admin_event()
        template_context = self._tournament_import_modal_context(
            event, importer_id, web_context.admin_tournament
        )
        return self._admin_base_event_render(
            web_context.template_context | template_context
        )

    @post(
        path=[
            '/tournament-import/{event_uniq_id:str}/{importer_id:str}',
            '/tournament-import/{event_uniq_id:str}/{tournament_id:int}/{importer_id:str}',
        ],
        name='admin-tournament-import',
        guards=[ActionGuard(AuthAction.ADD_TOURNAMENTS)],
    )
    async def admin_tournament_import(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, Any], Body(media_type=RequestEncodingType.MULTI_PART)
        ],
        tournament_id: int | None,
        importer_id: str,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        if web_context.admin_tournament and web_context.admin_tournament.started:
            raise ClientException('Import only possible before the tournament starts.')
        errors: dict[str, str] = {}
        event = web_context.get_admin_event()
        normalized_data = await WebContext.normalize_multipart_data(data)
        importer_type = TournamentImporterManager(event).get_type(importer_id)
        importer_options: list[TournamentImporterOption] = []
        for importer_option in importer_type().default_options():
            value = WebContext.form_data_to_value(
                normalized_data, importer_option.id, importer_option.type
            )
            importer_options.append(type(importer_option)(value))
        importer = importer_type(importer_options)
        try:
            importer.validate_options(event)
            tournament = importer.load_tournament(event, web_context.admin_tournament)
            Message.success(
                request,
                _('Tournament [{tournament}] successfully imported.').format(
                    tournament=tournament.uniq_id
                ),
            )
            web_context = TournamentAdminWebContext(
                request, tournament_id, reload_event=True
            )
            return self._admin_event_tournaments_render(web_context)
        except OptionError as error:
            errors[error.option.id] = str(error)
        except ImporterError as error:
            errors['alert'] = str(error)
        except SharlyChessException as error:
            logger.error(f'Tournament importer [{importer.id}] error: {error}')
            errors['alert'] = _('An error occurred. Consult the logs for more details.')
        finally:
            importer.on_import_finished()
        template_context = self._tournament_import_modal_context(
            event,
            importer_id,
            web_context.admin_tournament,
            data=normalized_data,
            errors=errors,
        )
        return self._admin_base_event_render(
            web_context.template_context | template_context
        )

    # -------------------------------------------------------------------------
    # Tournament criteria
    # -------------------------------------------------------------------------

    @classmethod
    def _validate_tournament_criterion_form_data(
        cls, event: Event, data: dict[str, str]
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        field = 'type'
        player_filter_id = data.get(field, '')
        try:
            PlayerFilterManager(event).get_type(player_filter_id)
        except KeyError:
            errors[field] = _('Please select a type of criterion.')
            return errors
        player_filter = cls.player_filter_from_data(event, data)
        try:
            player_filter.validate_options()
        except OptionError as error:
            errors[error.option.id] = str(error)
        return errors

    @staticmethod
    def player_filter_from_data(event: Event, data: dict[str, str]) -> PlayerFilter:
        player_filter_type = PlayerFilterManager(event).get_type(data['type'])
        options = []
        for option in player_filter_type().default_options():
            value = WebContext.form_data_to_value(data, option.id, option.type)
            options.append(type(option)(value))
        return player_filter_type(options)

    @staticmethod
    def _tournament_criterion_form_modal_context(
        request: HTMXRequest,
        event: Event,
        data: dict[str, str],
        action: FormAction,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        default_data = {
            option.id: WebContext.value_to_form_data(option.default_value)
            for option in PlayerFilterOptionManager(event).objects()
        } | {'type': ''}
        return {
            'modal': 'tournament_criterion_form',
            'action': action,
            'player_filter_select_options': {'': '-'}
            | PlayerFilterManager(event).options(),
            'player_filter_options': PlayerFilterOptionManager(event).objects(),
            'containers_by_type': {
                player_filter.id: [
                    option.container_id for option in player_filter.default_options()
                ]
                for player_filter in PlayerFilterManager(event).objects()
            }
            | {'': []},
            'add_other_active': (
                SessionHandler.get_session_admin_tournament_criterion_add_other_active(
                    request
                )
            ),
            'data': default_data | data,
            'errors': errors or {},
        }

    @post(
        path=(
            '/tournaments/tournament-criterion/create/{event_uniq_id:str}/{tournament_id:int}'
        ),
        name='admin-tournament-criterion-create',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_tournament_criterion_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        event = web_context.get_admin_event()
        add_other = 'add_other' in data
        SessionHandler.set_session_admin_tournament_criterion_add_other_active(
            request, add_other
        )
        flat_data = WebContext.flatten_list_data(data)
        if errors := self._validate_tournament_criterion_form_data(event, flat_data):
            return self._admin_base_event_render(
                web_context.template_context
                | self._tournament_criterion_form_modal_context(
                    request, event, flat_data, FormAction.CREATE, errors
                )
            )

        player_filter = self.player_filter_from_data(event, flat_data)
        criterion = web_context.get_admin_tournament().add_criterion(
            StoredTournamentCriterion(
                id=None,
                tournament_id=tournament_id,
                type=player_filter.id,
                options={option.id: option.value for option in player_filter.options},
            )
        )
        if add_other:
            template_context = self._tournament_criterion_form_modal_context(
                request, event, {}, FormAction.CREATE, errors
            ) | {'previous_criterion': criterion}
        else:
            template_context = {'modal': 'tournament_criteria'}
        return self._admin_base_event_render(
            web_context.template_context | template_context
        )

    @patch(
        path=(
            '/tournaments/tournament-criterion/update/{event_uniq_id:str}'
            '/{tournament_id:int}/{tournament_criterion_id:int}'
        ),
        name='admin-tournament-criterion-update',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_tournament_criterion_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
        tournament_criterion_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(
            request,
            tournament_id,
            tournament_criterion_id,
        )
        event = web_context.get_admin_event()

        flat_data = WebContext.flatten_list_data(data)
        if errors := self._validate_tournament_criterion_form_data(event, flat_data):
            self._admin_base_event_render(
                web_context.template_context
                | self._tournament_criterion_form_modal_context(
                    request, event, flat_data, FormAction.UPDATE, errors
                )
            )
        player_filter = self.player_filter_from_data(event, flat_data)
        tournament_criterion = web_context.get_admin_tournament_criterion()
        stored_tournament_criterion = tournament_criterion.stored_tournament_criterion
        stored_tournament_criterion.type = player_filter.id
        stored_tournament_criterion.options = {
            option.id: option.value for option in player_filter.options
        }
        tournament_criterion.update()
        return self._admin_base_event_render(
            web_context.template_context | {'modal': 'tournament_criteria'}
        )

    @delete(
        path=(
            '/tournaments/tournament-criterion/delete/{event_uniq_id:str}/{tournament_id:int}'
            '/{tournament_criterion_id:int}'
        ),
        name='admin-tournament-criterion-delete',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_tournament_criterion_delete(
        self,
        request: HTMXRequest,
        tournament_id: int,
        tournament_criterion_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(
            request,
            tournament_id,
            tournament_criterion_id,
        )
        web_context.get_admin_tournament().delete_criterion(tournament_criterion_id)
        return self._admin_base_event_render(
            web_context.template_context | {'modal': 'tournament_criteria'}
        )

    @get(
        path=(
            '/tournaments/tournament-criteria-modal/{event_uniq_id:str}/{tournament_id:int}'
        ),
        name='admin-tournament-criteria-modal',
    )
    async def htmx_admin_tournament_criteria_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        return self._admin_base_event_render(
            web_context.template_context | {'modal': 'tournament_criteria'}
        )

    @get(
        path=(
            '/tournaments/criterion-modal/create/{event_uniq_id:str}/{tournament_id:int}'
        ),
        name='admin-tournament-criterion-create-modal',
    )
    async def htmx_admin_tournament_criterion_create_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        event = web_context.get_admin_event()
        return self._admin_base_event_render(
            web_context.template_context
            | self._tournament_criterion_form_modal_context(
                request, event, {}, FormAction.CREATE
            )
        )

    @get(
        path=(
            '/tournaments/criterion-modal/update/{event_uniq_id:str}'
            '/{tournament_id:int}/{tournament_criterion_id:int}'
        ),
        name='admin-tournament-criterion-update-modal',
    )
    async def htmx_admin_tournament_criterion_update_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        tournament_criterion_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(
            request, tournament_id, tournament_criterion_id
        )
        event = web_context.get_admin_event()

        tournament_criterion = web_context.get_admin_tournament_criterion()
        data = {'type': tournament_criterion.player_filter.id} | {
            option.id: WebContext.value_to_form_data(option.value)
            for option in tournament_criterion.player_filter.options
        }
        return self._admin_base_event_render(
            web_context.template_context
            | self._tournament_criterion_form_modal_context(
                request, event, data, FormAction.UPDATE
            )
        )

    # -------------------------------------------------------------------------
    # Misc
    # -------------------------------------------------------------------------

    @get(
        path=[
            '/random-player/{event_uniq_id:str}',
            '/random-player/{event_uniq_id:str}/{tournament_id:int}',
        ],
        name='admin-random-player',
    )
    async def htmx_random_player(
        self,
        request: HTMXRequest,
        tournament_id: int | None,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)

        assert web_context.admin_event is not None
        admin_event: Event = web_context.admin_event
        admin_tournament: Tournament | None = web_context.admin_tournament

        if not admin_tournament:
            admin_tournament = random.choice(
                list(admin_event.tournaments_by_id.values())
            )

        players = admin_tournament.players if admin_tournament else None
        random_player = random.choice(list(players)) if players else None

        board: Board | None = None
        if random_player is not None:
            board = next(
                (
                    b
                    for b in admin_tournament.boards
                    if (
                        b.white_player is not None
                        and b.white_player.id == random_player.id
                    )
                    or (
                        b.black_player is not None
                        and b.black_player.id == random_player.id
                    )
                ),
                None,
            )

        opponent: Player | None = None
        if random_player and board is not None:
            if board.white_player and board.white_player.id != random_player.id:
                opponent = board.white_player
            elif board.black_player and board.black_player.id != random_player.id:
                opponent = board.black_player

        return HTMXTemplate(
            template_name='admin/tournaments/random_player_modal.html',
            context={
                'player_name': random_player.full_name if random_player else None,
                'random_player': random_player,
                'opponent_name': opponent.full_name if opponent else None,
                'tournament': admin_tournament,
                'admin_event': admin_event,
                'board': board,
            },
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
        )
