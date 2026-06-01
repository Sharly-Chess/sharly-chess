import json
import random
from collections import defaultdict
from datetime import datetime
from functools import partial
from tempfile import NamedTemporaryFile
from typing import Annotated, Any

from litestar import post, get, patch, delete
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotFoundException, ClientException, ValidationException
from litestar.params import Body
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
from litestar.response import Template, File, Redirect
from litestar.status_codes import HTTP_200_OK

from common.exception import SharlyChessException, OptionError, ImporterError, FormError
from common.i18n import _, ngettext
from common.logger import get_logger
from data.access_levels.actions import AuthAction
from data.board import Board, PlayerRatingType
from data.criteria.managers import TournamentCriterionManager
from data.event import Event
from data.input_output import (
    DataSourceManager,
    TournamentExporter,
    TournamentExporterManager,
    TournamentImporterManager,
)
from data.input_output.tournament_importer_options import (
    TournamentImporterOption,
    FileOption,
)
from data.input_output.tournament_importers import TournamentImporter
from data.input_output.trf.trf_importer import TrfTournamentImporter
from data.pairings import PairingSystem, PairingSystemManager
from data.pairings.systems import SwissPairingSystem
from data.player import TournamentPlayer
from data.tie_breaks import TieBreakManager, TieBreak, TieBreakOptionManager
from data.tie_breaks.sets import (
    TieBreakSetSource,
    available_tie_break_sets,
    get_tie_break_set,
    instantiate_tie_break,
    stored_tie_break_to_dict,
    TieBreakSet,
)
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.config.config_store import StoredTieBreakSet
from common.sharly_chess_config import SharlyChessConfig
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredTournament,
    StoredScreen,
    StoredPairing,
)
from plugins.manager import plugin_manager
from utils import Utils
from utils.date_time import format_date, format_date_range
from utils.enum import FormAction, Result, TournamentRating, ScreenType
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.guards import EventGuard, ActionGuard, TournamentActionGuard
from web.messages import Message
from web.session import (
    SessionTournamentsShowDetails,
    SessionTieBreakAddOtherActive,
    SessionDistributeType,
    SessionDistributeUseBalanceGroups,
    SessionDistributeUnselectedTournaments,
    SessionDistributeGroupsById,
    SessionDistributePlayerCountByTournamentId,
)
from web.utils import SelectOption

logger = get_logger()


class TournamentAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        tournament_id: int | None = None,
        tie_break_id: int | None = None,
        exporter_id: str | None = None,
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

        self.admin_tie_break_id = tie_break_id
        if tie_break_id:
            assert self.admin_tournament is not None
            if tie_break_id not in self.admin_tournament.tie_breaks_by_id:
                raise NotFoundException(
                    f'Unknown tie-break ID [{tie_break_id}] '
                    f'for tournament [{self.admin_tournament.name}].'
                )
        self.admin_exporter: TournamentExporter | None = None
        if exporter_id:
            try:
                self.admin_exporter = TournamentExporterManager(
                    self.get_admin_event()
                ).get_object(exporter_id)
            except KeyError:
                raise NotFoundException(f'Unknown tournament exporter [{exporter_id}].')

    def get_admin_tournament(self) -> Tournament:
        assert self.admin_tournament is not None
        return self.admin_tournament

    def get_admin_tie_break(self) -> TieBreak:
        assert self.admin_tie_break_id is not None
        return self.get_admin_tournament().tie_breaks_by_id[self.admin_tie_break_id]

    def get_admin_exporter(self) -> TournamentExporter:
        assert self.admin_exporter is not None
        return self.admin_exporter

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_tournament': self.admin_tournament,
            'admin_tie_break_id': self.admin_tie_break_id,
            'admin_exporter': self.admin_exporter,
            'allowed_tournaments': self.client.allowed_tournaments_for_action(
                AuthAction.VIEW_TOURNAMENTS_TAB
            ),
        }


class TournamentAdminController(BaseEventAdminController):
    guards = [
        EventGuard(),
        TournamentActionGuard(AuthAction.VIEW_TOURNAMENTS_TAB),
    ]

    @classmethod
    def _admin_event_tournaments_render(
        cls,
        web_context: TournamentAdminWebContext,
        template_context: dict[str, Any] | None = None,
    ) -> Template:
        event = web_context.get_admin_event()
        request = web_context.request
        plugin_context = Utils.concat_dicts(
            plugin_manager.hook_for_event(
                event, 'get_tournament_page_template_context'
            )()
        )
        plugin_card_fields_templates = plugin_manager.hook_for_event(
            event, 'get_tournament_card_fields_template'
        )()
        plugin_card_action_menu_items_templates = plugin_manager.hook_for_event(
            event, 'get_tournament_card_action_menu_items_template'
        )()
        plugin_tab_action_menu_items_templates = plugin_manager.hook_for_event(
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
                'get_tournament_card_connexion_templates': partial(
                    cls._get_tournament_card_connexion_templates, event=event
                ),
                'tournament_card_time_control_template': plugin_manager.hook_for_event(
                    event, 'get_tournament_card_time_control_template'
                )()
                or 'tournament_card_time_control.html',
                'plugin_card_fields_templates': plugin_card_fields_templates,
                'tournament_importers': tournament_importers,
                'tournament_exporters': tournament_exporters,
                'plugin_card_action_menu_items_templates': plugin_card_action_menu_items_templates,
                'plugin_tab_action_menu_items_templates': plugin_tab_action_menu_items_templates,
                'show_details': SessionTournamentsShowDetails(request).get(),
                'data_sources': DataSourceManager().objects(),
            }
            | plugin_context
            | (template_context or {})
        )
        return cls._admin_base_event_render(template_context)

    @staticmethod
    def _get_tournament_card_connexion_templates(
        tournament: Tournament, event: Event
    ) -> list[str]:
        return [
            template
            for template in plugin_manager.hook_for_event(
                event, 'get_tournament_card_connexion_template'
            )(tournament=tournament)
            if template is not None
        ]

    @get(
        path='/event/{event_uniq_id:str}/tournaments',
        name='admin-event-tournaments-tab',
    )
    async def htmx_admin_event_tournaments_tab(
        self,
        request: HTMXRequest,
        show_details: bool | None,
    ) -> Template:
        web_context = TournamentAdminWebContext(request)
        if show_details is not None:
            SessionTournamentsShowDetails(request).set(show_details)

        return self._admin_event_tournaments_render(web_context)

    @classmethod
    def _prepare_tournament_modal_data(
        cls,
        action: FormAction,
        web_context: TournamentAdminWebContext,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
        redirect_to: str | None = None,
    ):
        admin_event = web_context.get_admin_event()
        pairing_systems = PairingSystemManager(admin_event).objects()
        pairing_system: PairingSystem = SwissPairingSystem()
        tournament_criteria = TournamentCriterionManager(admin_event).objects()
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
            record_illegal_moves: int | None = None
            first_board_number: int | None = None
            paired_bye_result: float | None = None
            max_byes: int | None = None
            last_rounds_no_byes: int | None = None
            location: str | None = None
            player_rating_type: int | None = None
            pairing_variations: dict[str, str | None] = {
                system.variation_field_id: None for system in pairing_systems
            }
            three_points_for_a_win: bool | None = None
            pab_value: int | None = None
            override_unrated_rapid_blitz: bool = True
            stored_plugin_data: dict[str, dict[str, Any]] = {}
            if action == 'create':
                rounds = 7
                rating = TournamentRating.STANDARD.value
                start_date = admin_event.start_date
                stop_date = admin_event.stop_date
            else:
                admin_tournament = web_context.get_admin_tournament()
                stored_tournament = admin_tournament.stored_tournament
                time_control_trf25 = stored_tournament.time_control_trf25
                record_illegal_moves = stored_tournament.record_illegal_moves
                first_board_number = stored_tournament.first_board_number
                paired_bye_result = stored_tournament.paired_bye_result
                max_byes = stored_tournament.max_byes
                last_rounds_no_byes = stored_tournament.last_rounds_no_byes
                location = stored_tournament.location
                player_rating_type = stored_tournament.player_rating_type
                start_date = admin_tournament.start_date
                stop_date = admin_tournament.stop_date
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
                for criterion in tournament_criteria:
                    if criterion.id in stored_tournament.criteria:
                        value = criterion.value_from_stored_value(
                            stored_tournament.criteria[criterion.id]
                        )
                        criterion.set_value(value)
                stored_plugin_data = stored_tournament.plugin_data

            plugin_form_data: dict[str, str] = {}
            for (
                plugin_id,
                plugin_data_class,
            ) in Tournament.plugin_data_class_by_plugin_id().items():
                plugin_form_data |= plugin_data_class.from_stored_value(
                    stored_plugin_data.get(plugin_id, {})
                ).to_form_data(action=action)

            criteria_form_data: dict[str, str] = {}
            for criterion in tournament_criteria:
                criterion.add_to_form_data(criteria_form_data)

            round_datetimes: dict[int, datetime | None] = {}
            if action in ('update', 'clone'):
                tournament = web_context.get_admin_tournament()
                round_datetimes = tournament.round_datetimes
            schedule_form_data: dict[str, str] = {}
            for round_num in range(1, rounds + 1):
                dt = round_datetimes.get(round_num)
                schedule_form_data[f'round_{round_num}_datetime'] = (
                    WebContext.value_to_form_data(dt) if dt else ''
                )

            data: dict[str, str] = WebContext.values_dict_to_form_data(
                {
                    'name': name,
                    'time_control_trf25': time_control_trf25,
                    'record_illegal_moves': record_illegal_moves,
                    'first_board_number': first_board_number,
                    'paired_bye_result': paired_bye_result,
                    'max_byes': max_byes,
                    'last_rounds_no_byes': last_rounds_no_byes,
                    'location': location,
                    'player_rating_type': player_rating_type,
                    'rounds': rounds,
                    'rating': rating,
                    'pairing_system': pairing_system.id,
                    'three_points_for_a_win': three_points_for_a_win,
                    'pab_value': pab_value,
                    'override_unrated_rapid_blitz': override_unrated_rapid_blitz,
                    'date_range': WebContext.value_to_date_range_form_data(
                        start_date, stop_date
                    ),
                    'redirect_to': redirect_to,
                }
                | {field: variation for field, variation in pairing_variations.items()}
                | plugin_form_data
                | schedule_form_data
                | criteria_form_data
            )
            stored_tournament, errors = cls._admin_get_validated_tournament_data(
                action, web_context, data
            )

        schedule_min_date = admin_event.start_date
        schedule_max_date = admin_event.stop_date
        try:
            assert data is not None
            date_range = WebContext.form_data_to_date_range(data, 'date_range')
            if date_range:
                schedule_min_date, schedule_max_date = date_range
        except FormError:
            pass
        plugin_results = plugin_manager.hook_for_event(
            admin_event, 'get_tournament_form_fields_template_and_data'
        )(event=admin_event, tournament=web_context.admin_tournament)

        plugin_form_fields_templates = [template for template, __ in plugin_results]
        form_fields_templates_data = {
            key: value for __, data in plugin_results for key, value in data.items()
        }

        player_rating_type_options: dict[str, str] = {
            '': '',
            str(PlayerRatingType.FIDE.value): _('FIDE'),
            str(PlayerRatingType.NATIONAL.value): _(
                'National *** NAME FOR RATING TYPE NATIONAL'
            ),
        }
        player_rating_type_options[''] = _('Use default - {option}').format(
            option=player_rating_type_options[str(admin_event.player_rating_type.value)]
        )

        pab_value_options = {
            str(Result.WIN.value): _('Win'),
            str(Result.DRAW.value): _('Draw'),
            str(Result.LOSS.value): _('Loss'),
        }

        # data and errors are always populated by the if/else block above
        assert data is not None
        assert errors is not None
        rounds = int(data.get('rounds') or 1)
        template_context = {
            'rating_options': cls._get_rating_options(),
            'pairing_systems': pairing_systems,
            'pairing_system_options': PairingSystemManager(admin_event).options(),
            'plugin_form_fields_templates': plugin_form_fields_templates,
            'admin_tournament': None
            if action == 'clone'
            else web_context.admin_tournament,
            'cloned_tournament': web_context.admin_tournament
            if action == 'clone'
            else None,
            'player_rating_type_options': player_rating_type_options,
            'pab_value_options': pab_value_options,
            'modal': 'tournament',
            'action': action,
            'data': data,
            'errors': errors,
            'tournament_criteria': tournament_criteria,
            'force_criteria_open': any(
                criterion.is_used_in_form_data(data)
                for criterion in tournament_criteria
            ),
            # The current rounds count is needed to render the schedule inputs
            'schedule_rounds': rounds,
            'force_schedule_open': any(
                data.get(f'round_{n}_datetime') for n in range(1, rounds + 1)
            ),
            'schedule_min_date': format_date(schedule_min_date),
            'schedule_max_date': format_date(schedule_max_date),
        } | form_fields_templates_data

        return template_context

    @classmethod
    def _admin_get_validated_tournament_data(
        cls,
        action: str,
        web_context: TournamentAdminWebContext,
        data: dict[str, str] | None = None,
    ) -> tuple[StoredTournament, dict[str, str]]:
        event = web_context.get_admin_event()
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        start_date = event.start_date
        stop_date = event.stop_date
        rounds = WebContext.form_data_to_int(data, field := 'rounds') or 1
        tournament: Tournament | None = None

        index = len(event.tournaments)
        if rounds < 1:
            errors[field] = _('A positive integer is expected.')
        elif action == 'update':
            tournament = web_context.get_admin_tournament()
            index = tournament.index
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
        try:
            date_range = WebContext.form_data_to_date_range(data, field := 'date_range')
            if date_range:
                start_date, stop_date = date_range
        except FormError as e:
            errors[field] = str(e)

        pairing_system = PairingSystemManager(event).get_object(
            WebContext.form_data_to_str(data, 'pairing_system')
            or SwissPairingSystem.static_id()
        )
        pairing = WebContext.form_data_to_str(
            data, f'{pairing_system.id}_pairing_variation'
        )

        if action == 'update':
            tournament = web_context.get_admin_tournament()
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
            used_names = list(event.tournaments_by_name.keys())
            if action == 'update':
                used_names.remove(web_context.get_admin_tournament().name)
            if name in used_names:
                errors[field] = _('This name is already used.')
        time_control_trf25 = WebContext.form_data_to_str(data, 'time_control_trf25')
        record_illegal_moves = cls._admin_validate_record_illegal_moves_update_data(
            data, errors
        )
        first_board_number = WebContext.form_data_to_int(data, 'first_board_number')
        paired_bye_result = WebContext.form_data_to_int(data, 'paired_bye_result')
        max_byes = WebContext.form_data_to_int(data, 'max_byes')
        last_rounds_no_byes = WebContext.form_data_to_int(data, 'last_rounds_no_byes')
        location = WebContext.form_data_to_str(data, 'location')
        player_rating_type = WebContext.form_data_to_int(data, 'player_rating_type')
        three_points_for_a_win = WebContext.form_data_to_bool(
            data, 'three_points_for_a_win'
        )
        override_unrated_rapid_blitz = WebContext.form_data_to_bool(
            data, 'override_unrated_rapid_blitz'
        )
        pab_value = WebContext.form_data_to_int(data, 'pab_value')
        stored_criteria: dict[str, Any] = {}
        for criterion in TournamentCriterionManager(event).objects():
            value = criterion.value_from_form_data(data, errors)
            if value is None:
                continue
            criterion.set_value(value)
            stored_criteria[criterion.id] = criterion.stored_value

        # validation of rounds within the range of the event and sequentially ordered
        round_datetimes: dict[int, datetime | None] = {}
        prev_dt: datetime | None = None
        for round_num in range(1, rounds + 1):
            field = f'round_{round_num}_datetime'
            try:
                dt = WebContext.form_data_to_datetime(data, field)
                if dt is not None:
                    # validate for date range and sequential ordering
                    if not start_date <= dt.date() <= stop_date:
                        errors[field] = _(
                            'Time outside of tournament time range ({range}).'
                        ).format(range=format_date_range(start_date, stop_date))
                    elif prev_dt is not None and dt <= prev_dt:
                        errors[field] = _(
                            'Round #%(round)d must be scheduled after round #%(prev)d.'
                        ) % {'round': round_num, 'prev': round_num - 1}
                    else:
                        prev_dt = dt
                round_datetimes[round_num] = dt
            except FormError as e:
                errors[field] = str(e)
                round_datetimes[round_num] = None

        plugin_manager.hook_for_event(
            web_context.get_admin_event(), 'validate_tournament_form_fields'
        )(data=data, errors=errors)

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
            index=index,
            time_control_trf25=time_control_trf25,
            record_illegal_moves=record_illegal_moves,
            first_board_number=first_board_number,
            paired_bye_result=paired_bye_result,
            max_byes=max_byes,
            last_rounds_no_byes=last_rounds_no_byes,
            location=location,
            player_rating_type=player_rating_type,
            start_date=start_date,
            stop_date=stop_date,
            rounds=rounds or 1,
            rating=rating or TournamentRating.STANDARD.value,
            pairing=pairing or '',
            three_points_for_a_win=three_points_for_a_win,
            pab_value=pab_value or Result.WIN.value,
            override_unrated_rapid_blitz=override_unrated_rapid_blitz,
            plugin_data=plugin_data,
            round_datetimes=round_datetimes,
            criteria=stored_criteria,
        )
        return stored_tournament, errors

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
        guards=[TournamentActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_tournament_modal(
        self,
        request: HTMXRequest,
        action: FormAction,
        tournament_id: int,
        redirect_to: str | None = None,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id=tournament_id)
        template_context = self._prepare_tournament_modal_data(
            action, web_context, redirect_to=redirect_to
        )

        return self._admin_event_tournaments_render(
            web_context=web_context,
            template_context=template_context,
        )

    @get(
        path='/tournament-schedule-section/{event_uniq_id:str}',
        name='admin-tournament-schedule-section',
    )
    async def htmx_admin_tournament_schedule_section(
        self,
        request: HTMXRequest,
        tournament_id: int | None = None,
        rounds: str | None = None,
        date_range: str | None = None,
    ) -> Template:
        """Return just the schedule section for an outerHTML swap.

        Called by the rounds number input on change so the schedule fields
        update live without a full modal re-render.
        """
        web_context = TournamentAdminWebContext(request, tournament_id=tournament_id)
        tournament = web_context.admin_tournament
        event = web_context.get_admin_event()
        rounds_value = int(rounds or 0)
        if rounds_value < 1:
            if tournament:
                rounds_value = tournament.rounds
            else:
                rounds_value = 1

        min_date = event.start_date
        max_date = event.stop_date
        if date_range:
            try:
                form_date_range = WebContext.form_data_to_date_range(
                    {'range': date_range}, 'range'
                )
                if form_date_range:
                    min_date, max_date = form_date_range
            except FormError:
                pass

        # preserve datetimes when the user changes the number of rounds.
        # prefer values submitted from the form i.e user-typed, not yet saved
        # over values from the database.
        existing_datetimes: dict[int, datetime | None] = {}
        if tournament:
            existing_datetimes = tournament.round_datetimes

        # extract form-submitted round datetime values (sent via hx-include)
        form_datetimes: dict[str, str] = {}
        for key, value in request.query_params.items():
            if key.startswith('round_') and key.endswith('_datetime'):
                form_datetimes[key] = value

        schedule_form_data: dict[str, str] = {}
        has_any_value = False
        for round_num in range(1, rounds_value + 1):
            field = f'round_{round_num}_datetime'
            if field in form_datetimes and form_datetimes[field]:
                schedule_form_data[field] = form_datetimes[field]
                has_any_value = True
            else:
                dt = existing_datetimes.get(round_num)
                schedule_form_data[field] = (
                    WebContext.value_to_form_data(dt) if dt else ''
                )
                if dt:
                    has_any_value = True

        # evaluate if the schedule section should be open or collapsed
        # if collapsed it should remain collapsed
        schedule_collapsed_form = request.query_params.get('schedule_collapsed')
        if schedule_collapsed_form is not None:
            force_schedule_open = schedule_collapsed_form == 'false'
        else:
            force_schedule_open = has_any_value

        template_context = web_context.template_context | {
            'admin_event': event,
            'schedule_rounds': rounds_value,
            'data': schedule_form_data,
            'errors': {},
            'force_schedule_open': force_schedule_open,
            'schedule_min_date': format_date(min_date),
            'schedule_max_date': format_date(max_date),
        }

        return HTMXTemplate(
            template_name='/admin/tournaments/tournament_schedule_section.html',
            # replace the entire schedule section, looks cleaner
            re_swap='outerHTML',
            re_target='#schedule-section',
            context=template_context,
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
    ) -> Template | Redirect:
        web_context = TournamentAdminWebContext(request, tournament_id=tournament_id)
        event = web_context.get_admin_event()
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

        if message := plugin_manager.hook_for_event(event, 'signal_tournament_set')(
            event=event, stored_tournament=stored_tournament
        ):
            Message.warning(request, message)

        with EventDatabase(event.uniq_id, write=True) as database:
            if action == FormAction.UPDATE:
                tournament = web_context.get_admin_tournament()
                if tournament.rounds < stored_tournament.rounds:
                    database.delete_stored_pairings_after_round(
                        tournament.id, tournament.rounds
                    )
                    for tournament_player in tournament.tournament_players:
                        if not tournament_player.pairings_by_round[
                            tournament.rounds
                        ].zero_point_bye:
                            continue
                        for round_ in range(
                            tournament.rounds + 1, stored_tournament.rounds + 1
                        ):
                            database.add_stored_pairing(
                                StoredPairing(
                                    tournament_id=tournament.id,
                                    player_id=tournament_player.id,
                                    round_=round_,
                                    result=Result.ZERO_POINT_BYE.value,
                                    board_id=None,
                                )
                            )

                database.update_stored_tournament(stored_tournament)
                success_message = _(
                    'Tournament [{tournament}] has been updated.'
                ).format(tournament=stored_tournament.name)
            else:
                stored_tournament.id = database.add_stored_tournament(stored_tournament)
                tournament = Tournament(event, stored_tournament)
                if action == FormAction.CLONE:
                    base_tournament = web_context.get_admin_tournament()
                    for tie_break in base_tournament.tie_breaks_with_invalid:
                        stored_tie_break = tie_break.to_stored_value()
                        stored_tie_break.tournament_id = tournament.id
                        database.add_stored_tie_break(stored_tie_break)
                if 'add_screens' in data:
                    timer_id: int | None = None
                    if len(event.timers_by_id) == 1:
                        timer_id = list(event.timers_by_id.keys())[0]
                    for screen_type in [
                        ScreenType.CHECK_IN,
                        ScreenType.INPUT,
                        ScreenType.BOARDS,
                        ScreenType.PLAYERS,
                        ScreenType.RANKING,
                    ]:
                        stored_screen: StoredScreen = database.add_stored_screen(
                            StoredScreen(
                                id=None,
                                uniq_id=event.get_unused_screen_uniq_id(
                                    base_uniq_id=Utils.name_to_uniq_id(
                                        f'{tournament.name}-{screen_type.value}'
                                    )
                                ),
                                type=screen_type.value,
                                public=True,
                                name=f'{screen_type.name} ({tournament.name})',
                                columns=1,
                                font_size=None,
                                menu_link=True,
                                menu_text=None,
                                menu=f'@{screen_type.value}',
                                timer_id=timer_id,
                                input_exit_button=False,
                                players_show_unpaired=False,
                                players_player_format=self.get_default_players_screen_player_format(
                                    event
                                ).value,
                                players_board_format=self.get_default_players_screen_board_format(
                                    event
                                ).value,
                                players_opponent_format=self.get_default_players_screen_opponent_format(
                                    event
                                ).value,
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
                        database.add_stored_screen_set(stored_screen.id, tournament.id)
                    success_message = _(
                        'Tournament [{tournament}] has been created '
                        'and default screens have been added.'
                    ).format(tournament=tournament.name)
                else:
                    success_message = _(
                        'Tournament [{tournament}] has been created.'
                    ).format(tournament=tournament.name)

                tournament_id = tournament.id

        redirect_to = WebContext.form_data_to_str(data, 'redirect_to')
        if redirect_to:
            return Redirect(redirect_to, status_code=303)
        web_context = TournamentAdminWebContext(
            request, tournament_id, reload_event=True
        )
        if action == FormAction.CREATE:
            tournament = web_context.get_admin_tournament()
            return self._admin_base_event_render(
                web_context.template_context
                | self._tie_breaks_modal_context(
                    tournament, success_message=success_message
                )
            )
        Message.success(request, success_message)
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
    ) -> Template | Redirect:
        return self._admin_tournament_update(
            request,
            action=FormAction.CREATE,
            tournament_id=None,
            data=data,
        )

    @post(
        path='/tournament-clone/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-clone',
        guards=[ActionGuard(AuthAction.ADD_TOURNAMENTS)],
    )
    async def htmx_admin_tournament_clone(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
    ) -> Template | Redirect:
        return self._admin_tournament_update(
            request,
            action=FormAction.CLONE,
            tournament_id=tournament_id,
            data=data,
        )

    @patch(
        path='/tournament-update/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-update',
        guards=[TournamentActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_tournament_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
    ) -> Template | Redirect:
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

    @patch(
        path='/tournament-reorder/{event_uniq_id:str}',
        name='admin-tournament-reorder',
        guards=[ActionGuard(AuthAction.ADD_TOURNAMENTS)],
    )
    async def htmx_admin_tournament_reorder(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TournamentAdminWebContext(request)
        sorted_tournament_ids = data['item']
        with EventDatabase(web_context.get_admin_event().uniq_id, True) as database:
            for tournament in web_context.get_admin_event().tournaments_by_id.values():
                if tournament.id not in sorted_tournament_ids:
                    raise ValueError(f'Missing tournament id: {tournament.id}')
                index = sorted_tournament_ids.index(tournament.id)
                if index != tournament.index:
                    tournament.stored_tournament.index = index
                    database.update_stored_tournament(tournament.stored_tournament)
        web_context = TournamentAdminWebContext(request, reload_event=True)
        return self._admin_event_tournaments_render(web_context)

    # -------------------------------------------------------------------------
    # Tournament import/export
    # -------------------------------------------------------------------------

    @get(
        path='/tournament-export/data-loss-modal/{event_uniq_id:str}/{tournament_id:int}/{exporter_id:str}',
        name='tournament-export-data-loss-modal',
    )
    async def htmx_tournament_export_loss_warning_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        exporter_id: str,
    ) -> Template:
        web_context = TournamentAdminWebContext(
            request, tournament_id, exporter_id=exporter_id
        )
        return self._admin_base_event_render(
            web_context.template_context | {'modal': 'tournament-export-data-loss'}
        )

    @get(
        path='/tournament-export/{event_uniq_id:str}/{tournament_id:int}/{exporter_id:str}',
        name='admin-tournament-export',
    )
    async def admin_tournament_export(
        self,
        request: HTMXRequest,
        tournament_id: int,
        exporter_id: str,
    ) -> File | Template:
        web_context = TournamentAdminWebContext(
            request, tournament_id, exporter_id=exporter_id
        )
        tournament = web_context.get_admin_tournament()
        exporter = web_context.get_admin_exporter()

        temp_file = NamedTemporaryFile(
            delete=False,
            mode='wb' if exporter.is_binary_file else 'w',
            suffix=f'.{exporter.file_extension}',
            encoding=exporter.file_encoding,
        )
        try:
            with temp_file:
                exporter.dump_to_file(temp_file, tournament)
            return File(
                path=temp_file.name,
                filename=f'{exporter.file_name(tournament)}.{exporter.file_extension}',
            )
        except Exception as exception:
            temp_file.close()
            logger.exception(
                'Error when exporting tournament [%s] using exporter [%s]:\n%s',
                tournament.name,
                exporter.id,
                exception,
            )
            Message.error(
                request, _('An error occurred. Consult the logs for more details.')
            )
            return self.render_messages(request)

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
            tournament_id = importer.load_tournament(
                event, web_context.admin_tournament
            )
            web_context = TournamentAdminWebContext(
                request, tournament_id, reload_event=True
            )
            Message.success(
                request,
                _('Tournament [{tournament}] successfully imported.').format(
                    tournament=web_context.get_admin_tournament().name
                ),
            )
            return self._admin_event_tournaments_render(web_context)
        except OptionError as error:
            errors[error.option.id] = str(error)
        except ImporterError as error:
            errors['alert'] = str(error)
        except SharlyChessException as error:
            logger.exception(f'Tournament importer [{importer.id}] error: {error}')
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

    @post(
        path=[
            '/tournament-import/check-trf/{event_uniq_id:str}',
            '/tournament-import/check-trf/{event_uniq_id:str}/{tournament_id:int}',
        ],
        name='tournament-import-check-trf',
        guards=[ActionGuard(AuthAction.ADD_TOURNAMENTS)],
    )
    async def htmx_tournament_import_check_trf(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, Any], Body(media_type=RequestEncodingType.MULTI_PART)
        ],
        tournament_id: int | None,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        event = web_context.get_admin_event()
        tournament = web_context.admin_tournament
        normalized_data = await WebContext.normalize_multipart_data(data)
        file_path = WebContext.form_data_to_path(normalized_data, 'file')
        importer = TrfTournamentImporter([FileOption(file_path)])
        message: str | None = None
        message_type = 'error'
        try:
            importer.validate_options(event)
            stored_tournament, stored_players = importer.load_stored_tournament(
                event, getattr(tournament, 'stored_tournament', None)
            )
            importer.check_players_unicity(stored_players)
            importer.check_pairing_inconsistencies(stored_tournament)
            features = importer.get_not_importable_features(event)
            if features:
                message_type = 'warning'
                message = _("The following features won't be imported:")
                feature_list = ''.join(f'<li>{feature}</li>' for feature in features)
                message += f'<ul class="mb-0">{feature_list}</ul>'

        except (OptionError, ImporterError) as error:
            message = str(error)
        except Exception as error:
            logger.exception(f'Tournament importer [{importer.id}] error: {error}')
            message = _('An error occurred. Consult the logs for more details.')
        finally:
            importer.on_import_finished()
        return HTMXTemplate(
            template_name='/common/alert.html' if message else '/common/empty.html',
            re_swap='innerHTML',
            re_target='#alert-message',
            context={
                'message': message,
                'type': message_type,
                'hide_remove_button': True,
            },
        )

    # -------------------------------------------------------------------------
    # Tie breaks
    # -------------------------------------------------------------------------

    @classmethod
    def _validate_tie_break_form_data(
        cls,
        web_context: TournamentAdminWebContext,
        action: FormAction,
        data: dict[str, str],
    ) -> dict[str, str]:
        event = web_context.get_admin_event()
        tournament = web_context.get_admin_tournament()
        errors: dict[str, str] = {}
        field = 'type'
        tie_break_id = data.get(field, '')
        if not tie_break_id:
            return {field: _('A value is expected.')}
        try:
            TieBreakManager(event).get_type(tie_break_id)
        except KeyError:
            return {field: f'Unknown tie-break [{tie_break_id}].'}
        tie_break = cls._tie_break_from_data(event, data)
        if message := tournament.tie_break_invalid_message(tie_break):
            errors[field] = message
        else:
            existing_tie_breaks = [
                tie_break_
                for object_id, tie_break_ in tournament.tie_breaks_by_id.items()
                if (
                    action != FormAction.UPDATE
                    or object_id != web_context.admin_tie_break_id
                )
            ]
            if tie_break in existing_tie_breaks and not tie_break.allow_multiple:
                has_modifiers = any(
                    option.include_in_equals for option in tie_break.default_options()
                )
                errors[field] = (
                    _('This tie-break is already used with the same modifiers.')
                    if has_modifiers
                    else _('This tie-break is already used.')
                )
        try:
            tie_break.validate_options()
        except OptionError as error:
            errors[error.option.id] = str(error)
        return errors

    @staticmethod
    def _tie_break_from_data(event: Event, data: dict[str, str]) -> TieBreak:
        tie_break_type = TieBreakManager(event).get_type(data['type'])
        options = []
        for option in tie_break_type().default_options():
            value = WebContext.form_data_to_value(data, option.id, option.type)
            options.append(type(option)(value))
        return tie_break_type(options)

    @staticmethod
    def _tie_break_form_modal_context(
        web_context: TournamentAdminWebContext,
        data: dict[str, str],
        action: FormAction,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        event = web_context.get_admin_event()
        tournament = web_context.get_admin_tournament()
        request = web_context.request
        default_data = {
            option.id: WebContext.value_to_form_data(option.default_value)
            for option in TieBreakOptionManager(event).objects()
        } | {'type': ''}

        tie_break_select_options: dict[str, dict[str, SelectOption]] = defaultdict(dict)
        for tie_break in TieBreakManager(event).objects():
            if tournament.pairing_system in tie_break.forbidden_pairing_systems:
                continue
            tie_break_select_options[tie_break.category.name][tie_break.id] = (
                SelectOption(
                    f'{tie_break.acronym} - {tie_break.name}', tie_break.help_text
                )
            )
        return {
            'modal': 'tie_break_form',
            'action': action,
            'tie_break_select_options': {'': '-'} | tie_break_select_options,
            'tie_break_options': TieBreakOptionManager(event).objects(),
            'containers_by_type': {
                tie_break.id: [
                    option.container_id for option in tie_break.default_options()
                ]
                for tie_break in TieBreakManager(event).objects()
            }
            | {'': []},
            'add_other_active': SessionTieBreakAddOtherActive(request).get(),
            'data': default_data | data,
            'errors': errors or {},
        }

    @staticmethod
    def _tie_breaks_modal_context(
        tournament: Tournament,
        success_message: str | None = None,
        save_as_error: str | None = None,
        save_as_name_value: str | None = None,
    ) -> dict[str, Any]:
        """Build the additional context for the tie-breaks modal: the picker
        of tie-break sets and the user-set list for the save-as button."""
        grouped = available_tie_break_sets(tournament)

        select_options: dict[str, dict[str, SelectOption]] = {}
        for source in TieBreakSetSource:
            sets = grouped.get(source, [])
            if not sets:
                continue
            options: dict[str, SelectOption] = {}
            for tie_break_set in sets:
                options[f'{source.value}|{tie_break_set.key}'] = SelectOption(
                    name=tie_break_set.name,
                    tooltip=(
                        tie_break_set.disabled_reason
                        if tie_break_set.disabled
                        else tie_break_set.tooltip_message(tournament.event)
                    ),
                    disabled=tie_break_set.disabled,
                    subtitle=' - '.join(tie_break_set.tie_break_acronyms),
                )
            select_options[source.label] = options

        existing_custom_set_names = [
            tie_break_set.name
            for tie_break_set in grouped.get(TieBreakSetSource.CUSTOM, [])
        ]

        context: dict[str, Any] = {
            'modal': 'tie_breaks',
            'tie_break_set_select_options': select_options,
            'tie_break_set_custom_names': existing_custom_set_names,
            'tie_break_set_save_as_error': save_as_error,
            'tie_break_set_save_as_name_value': save_as_name_value or '',
        }
        if success_message:
            context['success_message'] = success_message
        return context

    @post(
        path=(
            '/tournaments/apply-tie-break-set/{event_uniq_id:str}/{tournament_id:int}'
        ),
        name='admin-apply-tie-break-set',
        guards=[TournamentActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_apply_tie_break_set(
        self,
        request: HTMXRequest,
        tournament_id: int,
        data: Annotated[
            dict[str, str | list[str]] | None,
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ] = None,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()
        if tournament.tie_breaks_by_id:
            raise ClientException(
                'Cannot apply a tie-break set when tie-breaks already exist.'
            )
        raw = (data or {}).get('tie_break_set', '')
        if isinstance(raw, list):
            raw = raw[0] if raw else ''
        selection = raw
        if '|' not in selection:
            raise ClientException(f'Invalid tie-break set selection [{selection}].')
        source, key = selection.split('|', 1)
        tie_break_set = get_tie_break_set(tournament, source, key)
        if tie_break_set is None:
            raise ClientException(
                f'Tie-break set [{key}] not found for source [{source}].'
            )
        if tie_break_set.disabled:
            raise ClientException(
                tie_break_set.disabled_reason or 'Tie-break set is disabled.'
            )
        for stored_tb in tie_break_set.stored_tie_breaks:
            tie_break = instantiate_tie_break(stored_tb, tournament.event)
            if tie_break is not None:
                tournament.add_tie_break(tie_break)
        return self._admin_base_event_render(
            web_context.template_context | self._tie_breaks_modal_context(tournament)
        )

    @post(
        path=(
            '/tournaments/save-tie-break-set/{event_uniq_id:str}/{tournament_id:int}'
        ),
        name='admin-save-tie-break-set',
        guards=[TournamentActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_save_tie_break_set(
        self,
        request: HTMXRequest,
        tournament_id: int,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()
        name = (WebContext.form_data_to_str(data, 'name') or '').strip()
        overwrite = WebContext.form_data_to_bool(data, 'overwrite')
        error: str | None = None
        if not name:
            error = _('Please choose a name for the set.')
        elif tournament.tie_breaks_invalid_messages:
            error = _(
                'The tournament has invalid tie-breaks; '
                'please fix them before saving as a set.'
            )
        elif not tournament.tie_breaks_by_id:
            error = _('The tournament has no tie-breaks to save.')
        success_message: str | None = None
        if not error:
            pairing_system_id = tournament.pairing_system.id
            stored_tie_breaks = [
                stored_tie_break_to_dict(tb.to_stored_value())
                for tb in tournament.tie_breaks_by_id.values()
            ]
            with ConfigDatabase(True) as database:
                existing = database.find_stored_tie_break_set_by_name(
                    pairing_system_id, name
                )
                if existing is not None and not overwrite:
                    error = _(
                        'A set named [{name}] already exists. '
                        'Tick the overwrite option to replace it.'
                    ).format(name=name)
                elif existing is not None:
                    existing.stored_tie_breaks = stored_tie_breaks
                    database.update_stored_tie_break_set(existing)
                    success_message = _('Set [{name}] has been updated.').format(
                        name=name
                    )
                else:
                    database.add_stored_tie_break_set(
                        StoredTieBreakSet(
                            id=None,
                            name=name,
                            pairing_system_id=pairing_system_id,
                            stored_tie_breaks=stored_tie_breaks,
                        )
                    )
                    success_message = _('Set [{name}] has been saved.').format(
                        name=name
                    )
            SharlyChessConfig().load_and_set_env()
        return self._admin_base_event_render(
            web_context.template_context
            | self._tie_breaks_modal_context(
                tournament,
                success_message=success_message,
                save_as_error=error,
                save_as_name_value=name if error else '',
            )
        )

    @post(
        path='/tournaments/tie-break/create/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tie-break-create',
        guards=[TournamentActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_tie_break_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        event = web_context.get_admin_event()
        tournament = web_context.get_admin_tournament()
        add_other = WebContext.resolve_add_other(
            data, SessionTieBreakAddOtherActive(request)
        )
        if errors := self._validate_tie_break_form_data(
            web_context, FormAction.CREATE, data
        ):
            return self._admin_base_event_render(
                web_context.template_context
                | self._tie_break_form_modal_context(
                    web_context, data, FormAction.CREATE, errors
                )
            )
        tie_break = self._tie_break_from_data(event, data)
        tournament.add_tie_break(tie_break)
        if add_other:
            template_context = self._tie_break_form_modal_context(
                web_context, {}, FormAction.CREATE, errors
            ) | {'previous_tie_break': tie_break}
        else:
            template_context = self._tie_breaks_modal_context(tournament)
        return self._admin_base_event_render(
            web_context.template_context | template_context
        )

    @post(
        path=(
            '/tournaments/tie-break/duplicate/{event_uniq_id:str}'
            '/{tournament_id:int}/{tie_break_id:int}'
        ),
        name='admin-tie-break-duplicate',
        guards=[TournamentActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_tie_break_duplicate(
        self,
        request: HTMXRequest,
        tournament_id: int,
        tie_break_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(
            request, tournament_id, tie_break_id=tie_break_id
        )
        tournament = web_context.get_admin_tournament()
        tie_break = web_context.get_admin_tie_break()
        if not tie_break.allow_multiple:
            raise ValidationException(
                f"Tie-breaks of type [{tie_break.id}] can't be duplicated."
            )
        tournament.add_tie_break(tie_break)
        return self._admin_base_event_render(
            web_context.template_context | self._tie_breaks_modal_context(tournament)
        )

    @patch(
        path=(
            '/tournaments/tie-break/update/{event_uniq_id:str}'
            '/{tournament_id:int}/{tie_break_id:int}'
        ),
        name='admin-tie-break-update',
        guards=[TournamentActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_tie_break_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: int,
        tie_break_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(
            request,
            tournament_id,
            tie_break_id=tie_break_id,
        )
        event = web_context.get_admin_event()
        tournament = web_context.get_admin_tournament()
        if errors := self._validate_tie_break_form_data(
            web_context, FormAction.UPDATE, data
        ):
            return self._admin_base_event_render(
                web_context.template_context
                | self._tie_break_form_modal_context(
                    web_context, data, FormAction.UPDATE, errors
                )
            )
        tie_break = self._tie_break_from_data(event, data)
        tournament.update_tie_break(tie_break_id, tie_break)
        return self._admin_base_event_render(
            web_context.template_context | self._tie_breaks_modal_context(tournament)
        )

    @delete(
        path=(
            '/tournaments/tie-break/delete/{event_uniq_id:str}'
            '/{tournament_id:int}/{tie_break_id:int}'
        ),
        name='admin-tie-break-delete',
        guards=[TournamentActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_tie_break_delete(
        self,
        request: HTMXRequest,
        tournament_id: int,
        tie_break_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(
            request,
            tournament_id,
            tie_break_id=tie_break_id,
        )
        tournament = web_context.get_admin_tournament()
        tournament.delete_tie_break(tie_break_id)
        return self._admin_base_event_render(
            web_context.template_context | self._tie_breaks_modal_context(tournament)
        )

    @patch(
        path='/tournament-reorder-tie-breaks/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-reorder-tie-breaks',
        guards=[TournamentActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_tournament_reorder_tie_breaks(
        self,
        request: HTMXRequest,
        tournament_id: int,
        data: Annotated[
            dict[str, list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()
        tournament.reorder_tie_breaks(data.get('tie_break_ids', []))
        return self._admin_base_event_render(
            web_context.template_context | self._tie_breaks_modal_context(tournament)
        )

    @get(
        path='/tournaments/tie-breaks-modal/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tie-breaks-modal',
    )
    async def htmx_admin_tie_breaks_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()
        return self._admin_base_event_render(
            web_context.template_context | self._tie_breaks_modal_context(tournament)
        )

    @staticmethod
    def _tie_break_sets_modal_context() -> dict[str, Any]:
        """Context for the custom TB-set management modal: lists all custom
        sets for the current pairing system."""
        system_name_by_id = PairingSystemManager(None).options()
        custom_sets_by_pairing_system_name: dict[str, list[TieBreakSet]] = {
            system_name: [] for system_name in system_name_by_id.values()
        }
        for tie_break_set in SharlyChessConfig().custom_tie_break_sets:
            from data.tie_breaks.sets import fill_acronyms

            fill_acronyms(tie_break_set, event=None)
            system_name = system_name_by_id[tie_break_set.pairing_system_id]
            custom_sets_by_pairing_system_name[system_name].append(tie_break_set)

        return {
            'modal': 'tie_break_sets',
            'custom_sets_by_pairing_system_name': {
                name: sets
                for name, sets in custom_sets_by_pairing_system_name.items()
                if sets
            },
        }

    @get(
        path=(
            '/tournaments/tie-break-sets-modal/{event_uniq_id:str}/{tournament_id:int}'
        ),
        name='admin-tie-break-sets-modal',
        guards=[TournamentActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_tie_break_sets_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        return self._admin_base_event_render(
            web_context.template_context | self._tie_break_sets_modal_context()
        )

    @delete(
        path=(
            '/tournaments/tie-break-set/delete/{event_uniq_id:str}'
            '/{tournament_id:int}/{tie_break_set_id:int}'
        ),
        name='admin-tie-break-set-delete',
        guards=[TournamentActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_tie_break_set_delete(
        self,
        request: HTMXRequest,
        tournament_id: int,
        tie_break_set_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        with ConfigDatabase(True) as database:
            database.delete_stored_tie_break_set(tie_break_set_id)
        SharlyChessConfig().load_and_set_env()
        return self._admin_base_event_render(
            web_context.template_context | self._tie_break_sets_modal_context()
        )

    @get(
        path='/tournaments/tie-break-modal/create/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tie-break-create-modal',
    )
    async def htmx_admin_tie_break_create_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        return self._admin_base_event_render(
            web_context.template_context
            | self._tie_break_form_modal_context(web_context, {}, FormAction.CREATE)
        )

    @get(
        path=(
            '/tournaments/tie-break-modal/update/{event_uniq_id:str}'
            '/{tournament_id:int}/{tie_break_id:int}'
        ),
        name='admin-tie-break-update-modal',
    )
    async def htmx_admin_tie_break_update_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
        tie_break_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(
            request, tournament_id, tie_break_id=tie_break_id
        )
        tie_break = web_context.get_admin_tie_break()
        data = {'type': tie_break.id} | {
            option.id: WebContext.value_to_form_data(option.value)
            for option in tie_break.options
        }
        return self._admin_base_event_render(
            web_context.template_context
            | self._tie_break_form_modal_context(web_context, data, FormAction.UPDATE)
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
        event = web_context.get_admin_event()
        tournament = web_context.admin_tournament
        if not tournament:
            allowed_tournaments = web_context.client.allowed_tournaments_for_action(
                AuthAction.VIEW_TOURNAMENTS_TAB
            )
            tournament = random.choice(
                [
                    tournament_
                    for tournament_ in allowed_tournaments
                    if tournament_.tournament_players
                ]
            )
        tournament_player: TournamentPlayer | None = None
        if tournament and tournament.tournament_players:
            tournament_player = random.choice(list(tournament.tournament_players))

        board: Board | None = None
        opponent: TournamentPlayer | None = None
        if tournament_player and tournament.started:
            pairing = tournament_player.pairings[tournament.current_round]
            board = pairing.board
            opponent = pairing.opponent

        return HTMXTemplate(
            template_name='admin/tournaments/random_player_modal.html',
            context={
                'random_player': tournament_player,
                'opponent_name': opponent.full_name if opponent else None,
                'tournament': tournament,
                'admin_event': event,
                'board': board,
            },
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
        )

    @get(
        path='/delete-unpaired-players/{event_uniq_id:str}/{tournament_id:int}',
        name='delete-unpaired-players',
    )
    async def htmx_delete_unpaired_players(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        event = web_context.get_admin_event()
        tournament = web_context.get_admin_tournament()
        if not tournament.started:
            raise ClientException(f'Tournament [{tournament.name}] is not started.')
        players = [
            player
            for player in tournament.tournament_players
            if not player.has_real_pairings
        ]
        with EventDatabase(event.uniq_id, True) as database:
            for player in players:
                database.delete_stored_player(player.id)
        Message.success(
            request,
            ngettext(
                '{count} player deleted.',
                '{count} players deleted.',
                len(players),
            ).format(count=len(players)),
        )
        web_context = TournamentAdminWebContext(
            request, tournament_id, reload_event=True
        )
        return self._admin_event_tournaments_render(web_context)

    @classmethod
    def _player_distribution_modal_context(
        cls, web_context: TournamentAdminWebContext
    ) -> dict[str, Any]:
        request = web_context.request
        event = web_context.get_admin_event()
        session_groups_by_id = SessionDistributeGroupsById(request, event).get()
        groups_by_id: dict[int, list[int]] = {}
        tournament_ids = list(event.tournaments_by_id)
        for group_id, group_tournament_ids in session_groups_by_id.items():
            group = [
                tournament_id
                for tournament_id in group_tournament_ids
                if tournament_id in tournament_ids
            ]
            if len(group) > 1:
                groups_by_id[int(group_id)] = group
        tournament_players = event.tournament_players
        criteria_player_ids_by_tournament_id = {
            tournament.id: [
                player.id
                for player in tournament_players
                if player.matches_tournament_criteria
            ]
            for tournament in event.tournaments
        }
        session_count_by_tournament_id = SessionDistributePlayerCountByTournamentId(
            request, event
        ).get()
        return {
            'modal': 'distribute-players',
            'distribution_type_options': {
                'rating': SelectOption(
                    _('Descending rating'),
                    _(
                        'Distribute the players by descending rating and '
                        'choose the number of players participating in each tournament.'
                    ),
                ),
                'criteria': SelectOption(
                    _('Criteria'),
                    _(
                        'Allocate players to the first tournament '
                        'for which the criteria are met.'
                    ),
                ),
            },
            'groups_by_id': groups_by_id,
            'unselected_tournament_ids': SessionDistributeUnselectedTournaments(
                request, event
            ).get(),
            'player_count_by_tournament_id': {
                int(tournament_id): player_count
                for tournament_id, player_count in session_count_by_tournament_id.items()
                if int(tournament_id) in event.tournaments_by_id
            },
            'criteria_player_ids_by_tournament_id': criteria_player_ids_by_tournament_id,
            'player_ids': list(event.players),
            'data': WebContext.values_dict_to_form_data(
                {
                    'distribution_type': SessionDistributeType(request).get(),
                    'use_balance_groups': SessionDistributeUseBalanceGroups(
                        request
                    ).get(),
                }
            ),
            'errors': {},
        }

    @get(
        path='/distribute-players-modal/{event_uniq_id:str}',
        name='admin-distribute-players-modal',
    )
    async def htmx_admin_distribute_players_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = TournamentAdminWebContext(request)
        return self._admin_event_tournaments_render(
            web_context,
            self._player_distribution_modal_context(web_context),
        )

    @staticmethod
    def _move_next_player_to_tournament(
        tournament_players: list[TournamentPlayer],
        tournament: Tournament,
    ) -> bool:
        """Moves the next player of the list to the target tournament, returns True on success, False otherwise."""
        try:
            tournament_player: TournamentPlayer = tournament_players.pop(0)
        except IndexError:
            logger.debug('No more players.')
            return False
        if tournament_player.tournament != tournament:
            logger.debug(
                'Moving player [%s] to tournament [%s]...',
                tournament_player.full_name,
                tournament.name,
            )
            tournament.event.move_player_to_tournament(tournament_player, tournament)
        else:
            logger.debug(
                'Player [%s] already in tournament [%s]...',
                tournament_player.full_name,
                tournament.name,
            )
        return True

    @classmethod
    def _distribute_players_by_rating(
        cls,
        event: Event,
        player_count_by_tournament_id: dict[int, int],
        groups_by_id: dict[str, list[int]],
    ):
        """Distribute the players among the tournaments with the given settings."""
        tournament_players: list[TournamentPlayer] = sorted(
            event.tournament_players,
            key=lambda player: player.starting_rank_sort_key,
        )
        group_id_by_tournament_id = {
            tournament.id: next(
                (
                    group_id
                    for group_id, tournament_ids in groups_by_id.items()
                    if tournament.id in tournament_ids
                ),
                None,
            )
            for tournament in event.sorted_tournaments
        }
        tournament_groups: list[list[Tournament]] = []
        previous_group_id: str | None = None
        for tournament in event.sorted_tournaments:
            group_id = group_id_by_tournament_id[tournament.id]
            if group_id is not None and group_id == previous_group_id:
                tournament_groups[-1].append(tournament)
            else:
                previous_group_id = group_id
                tournament_groups.append([tournament])
        for tournament_group in tournament_groups:
            while tournament_group:
                tournament_group = [
                    tournament
                    for tournament in tournament_group
                    if player_count_by_tournament_id[tournament.id] > 0
                ]
                for tournament in tournament_group:
                    cls._move_next_player_to_tournament(tournament_players, tournament)
                    player_count_by_tournament_id[tournament.id] -= 1

    @post(
        path='/distribute-players/{event_uniq_id:str}',
        name='admin-distribute-players',
    )
    async def htmx_admin_distribute_players(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TournamentAdminWebContext(request)
        event = web_context.get_admin_event()
        flat_data = WebContext.flatten_list_data(data)

        distribution_type = (
            WebContext.form_data_to_str(flat_data, 'distribution_type') or ''
        )
        groups_by_id = json.loads(flat_data.get('groups_by_id', '{}'))
        tournament_ids = WebContext.form_data_to_list_int(flat_data, 'tournament_ids')
        use_balance_groups = WebContext.form_data_to_bool(
            flat_data, 'use_balance_groups'
        )
        user_player_count_by_tournament_id: dict[str, str] = {}
        for tournament in event.tournaments:
            count = WebContext.form_data_to_int(
                flat_data, f'user_player_count_{tournament.id}'
            )
            if count is not None:
                user_player_count_by_tournament_id[str(tournament.id)] = str(count)

        SessionDistributeType(request).set(distribution_type)
        SessionDistributeGroupsById(request, event).set(groups_by_id)
        SessionDistributeUseBalanceGroups(request).set(use_balance_groups)
        SessionDistributeUnselectedTournaments(request, event).set(
            [
                tournament_id
                for tournament_id in event.tournaments_by_id
                if tournament_id not in tournament_ids
            ]
        )
        SessionDistributePlayerCountByTournamentId(request, event).set(
            user_player_count_by_tournament_id
        )

        if distribution_type == 'rating':
            player_count_by_tournament_id = {
                tournament.id: WebContext.form_data_to_int(
                    flat_data, f'player_count_{tournament.id}'
                )
                or 0
                for tournament in event.sorted_tournaments
            }
            self._distribute_players_by_rating(
                event,
                player_count_by_tournament_id,
                groups_by_id if use_balance_groups else {},
            )
        else:
            tournament_players = event.tournament_players
            matched_player_ids: list[int] = []
            for tournament in event.sorted_tournaments:
                if tournament.id not in tournament_ids:
                    continue
                for player in tournament_players:
                    if player.id in matched_player_ids:
                        continue
                    if player.matches_tournament_criteria:
                        matched_player_ids.append(player.id)
                        if player.tournament.id != tournament.id:
                            event.move_player_to_tournament(player, tournament)
        Message.success(
            request, _('Players successfully distributed among the tournaments.')
        )
        return self._admin_event_tournaments_render(web_context)
