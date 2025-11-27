import copy
import random
from collections import defaultdict
from datetime import date
from functools import partial
from tempfile import NamedTemporaryFile
from typing import Annotated, Any

from litestar import post, get, patch, delete
from litestar.exceptions import NotFoundException, ClientException, ValidationException
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, File
from litestar.status_codes import HTTP_200_OK

from common.exception import SharlyChessException, OptionError, ImporterError, FormError
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
from data.player import TournamentPlayer
from data.criteria.managers import (
    PlayerFilter,
    TournamentPlayerFilterManager,
    PlayerFilterOptionManager,
)
from data.tie_breaks import TieBreakManager, TieBreak, TieBreakOptionManager
from data.tournament import Tournament
from data.tournament_criterion import TournamentCriterion
from utils import Utils
from utils.enum import FormAction, Result, TournamentRating
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredTournament,
    StoredScreen,
    StoredTournamentCriterion,
    StoredPairing,
)
from plugins.manager import plugin_manager
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.guards import EventGuard, ActionGuard
from web.messages import Message
from web.session import SessionHandler
from web.utils import SelectOption

logger = get_logger()


class TournamentAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        tournament_id: int | None = None,
        criterion_id: int | None = None,
        tie_break_id: int | None = None,
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
        self.admin_tie_break_id = tie_break_id
        if tie_break_id:
            assert self.admin_tournament is not None
            if tie_break_id not in self.admin_tournament.tie_breaks_by_id:
                raise NotFoundException(
                    f'Unknown tie-break ID [{tie_break_id}] '
                    f'for tournament [{self.admin_tournament.name}].'
                )

    def get_admin_tournament(self) -> Tournament:
        assert self.admin_tournament is not None
        return self.admin_tournament

    def get_admin_tournament_criterion(self) -> TournamentCriterion:
        assert self.admin_tournament_criterion is not None
        return self.admin_tournament_criterion

    def get_admin_tie_break(self) -> TieBreak:
        assert self.admin_tie_break_id is not None
        return self.get_admin_tournament().tie_breaks_by_id[self.admin_tie_break_id]

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_tournament': self.admin_tournament,
            'admin_tournament_criterion': self.admin_tournament_criterion,
            'admin_tie_break_id': self.admin_tie_break_id,
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
                'plugin_card_fields_templates': plugin_card_fields_templates,
                'tournament_importers': tournament_importers,
                'tournament_exporters': tournament_exporters,
                'plugin_card_action_menu_items_templates': plugin_card_action_menu_items_templates,
                'plugin_tab_action_menu_items_templates': plugin_tab_action_menu_items_templates,
                'admin_tournaments_show_details': (
                    SessionHandler.get_session_admin_tournaments_show_details(
                        web_context.request
                    )
                ),
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
            record_illegal_moves: int | None = None
            rules: str | None = None
            first_board_number: int | None = None
            paired_bye_result: float | None = None
            max_byes: int | None = None
            last_rounds_no_byes: int | None = None
            location: str | None = None
            player_rating_type: int | None = None
            date_range_default = True
            date_range: str | None = None
            pairing_variations: dict[str, str | None] = {
                system.variation_field_id: None for system in pairing_systems
            }
            three_points_for_a_win: bool | None = None
            pab_value: int | None = None
            override_unrated_rapid_blitz: bool | None = None
            stored_plugin_data: dict[str, dict[str, Any]] = {}
            if action == 'create':
                rounds = 7
                rating = TournamentRating.STANDARD.value
            else:
                admin_tournament = web_context.get_admin_tournament()
                stored_tournament = admin_tournament.stored_tournament
                time_control_trf25 = stored_tournament.time_control_trf25
                record_illegal_moves = stored_tournament.record_illegal_moves
                rules = stored_tournament.rules
                first_board_number = stored_tournament.first_board_number
                paired_bye_result = stored_tournament.paired_bye_result
                max_byes = stored_tournament.max_byes
                last_rounds_no_byes = stored_tournament.last_rounds_no_byes
                location = stored_tournament.location
                player_rating_type = stored_tournament.player_rating_type
                date_range_default = (
                    not stored_tournament.start_date and not stored_tournament.stop_date
                )
                if not date_range_default:
                    date_range = WebContext.value_to_date_range_form_data(
                        admin_tournament.start_date, admin_tournament.stop_date
                    )
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

            plugin_form_data: dict[str, str] = {}
            for (
                plugin_id,
                plugin_data_class,
            ) in Tournament.plugin_data_class_by_plugin_id().items():
                plugin_form_data |= plugin_data_class.from_stored_value(
                    stored_plugin_data.get(plugin_id, {})
                ).to_form_data(action=action)

            data: dict[str, str] = WebContext.values_dict_to_form_data(
                {
                    'name': name,
                    'time_control_trf25': time_control_trf25,
                    'record_illegal_moves': record_illegal_moves,
                    'rules': rules,
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
                    'date_range': date_range,
                    'date_range_checkbox': date_range_default,
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

        override_unrated_rapid_blitz_options = {
            '': '',
            WebContext.value_to_form_data(True): _('Use standard ratings'),
            WebContext.value_to_form_data(False): _('Fallback to estimated ratings'),
        }

        override_unrated_rapid_blitz_options[''] = _('Use default - {option}').format(
            option=override_unrated_rapid_blitz_options[
                WebContext.value_to_form_data(admin_event.override_unrated_rapid_blitz)
            ]
        )

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

        three_points_for_a_win_options = {
            '': '',
            WebContext.value_to_form_data(True): _('Three points for a win (3-1-0)'),
            WebContext.value_to_form_data(False): _('Standard points (1-0.5-0)'),
        }
        three_points_for_a_win_options[''] = _('Use default - {option}').format(
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
        pab_value_options[''] = _('Use default - {option}').format(
            option=pab_value_options[str(admin_event.pab_value.value)]
        )

        template_context = {
            'rating_options': cls._get_rating_options(),
            'override_unrated_rapid_blitz_options': override_unrated_rapid_blitz_options,
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
        start_date: date | None = None
        stop_date: date | None = None
        rounds = WebContext.form_data_to_int(data, field := 'rounds') or 1
        tournament: Tournament | None = None

        index = len(web_context.admin_event.tournaments)
        if rounds < 1:
            errors[field] = _('A positive integer is expected.')
        elif action == 'update':
            tournament = web_context.admin_tournament
            assert tournament is not None
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
        event = web_context.admin_event
        try:
            date_range = WebContext.form_data_to_date_range(data, field := 'date_range')
            if date_range:
                for date_ in date_range:
                    if not event.start_date <= date_ <= event.stop_date:
                        errors[field] = _(
                            'Time outside of event time range ({range}).'
                        ).format(range=event.date_range_str)
                start_date, stop_date = date_range
        except FormError as e:
            errors[field] = str(e)

        pairing_system = PairingSystemManager(web_context.admin_event).get_object(
            WebContext.form_data_to_str(data, 'pairing_system')
            or SwissPairingSystem.static_id()
        )
        pairing = WebContext.form_data_to_str(
            data, f'{pairing_system.id}_pairing_variation'
        )

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
            index=index,
            time_control_trf25=time_control_trf25,
            record_illegal_moves=record_illegal_moves,
            rules=rules,
            first_board_number=first_board_number,
            paired_bye_result=paired_bye_result,
            max_byes=max_byes,
            last_rounds_no_byes=last_rounds_no_byes,
            check_in_open=check_in_open,
            location=location,
            player_rating_type=player_rating_type,
            start_date=start_date,
            stop_date=stop_date,
            rounds=rounds or 1,
            rating=rating or TournamentRating.STANDARD.value,
            pairing=pairing or '',
            three_points_for_a_win=three_points_for_a_win,
            pab_value=pab_value,
            override_unrated_rapid_blitz=override_unrated_rapid_blitz,
            plugin_data=plugin_data,
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
    )
    async def htmx_admin_tournament_modal(
        self,
        request: HTMXRequest,
        action: FormAction,
        tournament_id: int,
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

                stored_tournament = database.update_stored_tournament(stored_tournament)
                success_message = _(
                    'Tournament [{tournament}] has been updated.'
                ).format(tournament=stored_tournament.name)
            else:
                stored_tournament = database.add_stored_tournament(stored_tournament)
                tournament = Tournament(event, stored_tournament)
                if action == FormAction.CLONE:
                    base_tournament = web_context.get_admin_tournament()
                    for tie_break in base_tournament.tie_breaks_with_invalid:
                        stored_tie_break = tie_break.to_stored_value()
                        stored_tie_break.tournament_id = tournament.id
                        database.add_stored_tie_break(stored_tie_break)
                    for criterion in base_tournament.criteria:
                        stored_criterion = copy.copy(
                            criterion.stored_tournament_criterion
                        )
                        stored_criterion.tournament_id = tournament.id
                        database.add_stored_tournament_criterion(stored_criterion)
                if 'add_screens' in data:
                    timer_id: int | None = None
                    if len(event.timers_by_id) == 1:
                        timer_id = list(event.timers_by_id.keys())[0]
                    for type_, menu, name in [
                        (
                            'input',
                            '@input',
                            _('Check-in / Results entry ({tournament_name})').format(
                                tournament_name=tournament.name
                            ),
                        ),
                        (
                            'boards',
                            '@boards',
                            _('Pairings by board ({tournament_name})').format(
                                tournament_name=tournament.name
                            ),
                        ),
                        (
                            'players',
                            '@players',
                            _('Pairings by player ({tournament_name})').format(
                                tournament_name=tournament.name
                            ),
                        ),
                        (
                            'ranking',
                            '@ranking',
                            _('Ranking ({tournament_name})').format(
                                tournament_name=tournament.name
                            ),
                        ),
                    ]:
                        stored_screen: StoredScreen = database.add_stored_screen(
                            StoredScreen(
                                id=None,
                                uniq_id=event.get_unused_screen_uniq_id(
                                    base_uniq_id=Utils.name_to_uniq_id(
                                        f'{tournament.name}-{type_}'
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

        web_context = TournamentAdminWebContext(
            request, tournament_id, reload_event=True
        )
        if action == FormAction.CREATE:
            return self._admin_base_event_render(
                web_context.template_context
                | {
                    'modal': 'tie_breaks',
                    'success_message': success_message,
                }
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
    ) -> Template:
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
    ) -> Template:
        return self._admin_tournament_update(
            request,
            action=FormAction.CLONE,
            tournament_id=tournament_id,
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

    @patch(
        path='/tournament-reorder/{event_uniq_id:str}',
        name='admin-tournament-reorder',
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
        path='/tournament-export/{event_uniq_id:str}/{tournament_id:int}/{exporter_id:str}',
        name='admin-tournament-export',
    )
    async def admin_tournament_export(
        self,
        request: HTMXRequest,
        tournament_id: int,
        exporter_id: str,
    ) -> File | Template:
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
        try:
            with temp_file:
                exporter.dump_to_file(temp_file, tournament)
            return File(
                path=temp_file.name,
                filename=f'{exporter.file_name(tournament)}.{exporter.file_extension}',
            )
        except Exception as exception:
            temp_file.close()
            logger.error(
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
            'add_other_active': (
                SessionHandler.get_session_admin_tie_break_add_other_active(
                    web_context.request
                )
            ),
            'data': default_data | data,
            'errors': errors or {},
        }

    @post(
        path='/tournaments/create-default-tie-breaks/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-create-default-tie-breaks',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_create_default_tie_breaks(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()
        for tie_break in tournament.pairing_system.recommended_tie_breaks:
            tournament.add_tie_break(tie_break)
        return self._admin_base_event_render(
            web_context.template_context | {'modal': 'tie_breaks'}
        )

    @post(
        path='/tournaments/tie-break/create/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tie-break-create',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
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
        add_other = 'add_other' in data
        SessionHandler.set_session_admin_tie_break_add_other_active(request, add_other)
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
            template_context = {'modal': 'tie_breaks'}
        return self._admin_base_event_render(
            web_context.template_context | template_context
        )

    @post(
        path=(
            '/tournaments/tie-break/duplicate/{event_uniq_id:str}'
            '/{tournament_id:int}/{tie_break_id:int}'
        ),
        name='admin-tie-break-duplicate',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
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
            web_context.template_context | {'modal': 'tie_breaks'}
        )

    @patch(
        path=(
            '/tournaments/tie-break/update/{event_uniq_id:str}'
            '/{tournament_id:int}/{tie_break_id:int}'
        ),
        name='admin-tie-break-update',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
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
            web_context.template_context | {'modal': 'tie_breaks'}
        )

    @delete(
        path=(
            '/tournaments/tie-break/delete/{event_uniq_id:str}'
            '/{tournament_id:int}/{tie_break_id:int}'
        ),
        name='admin-tie-break-delete',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
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
        web_context.get_admin_tournament().delete_tie_break(tie_break_id)
        return self._admin_base_event_render(
            web_context.template_context | {'modal': 'tie_breaks'}
        )

    @patch(
        path='/tournament-reorder-tie-breaks/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-tournament-reorder-tie-breaks',
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
            web_context.template_context | {'modal': 'tie_breaks'}
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
        return self._admin_base_event_render(
            web_context.template_context | {'modal': 'tie_breaks'}
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
            TournamentPlayerFilterManager(event).get_type(player_filter_id)
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
        player_filter_type = TournamentPlayerFilterManager(event).get_type(data['type'])
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
            | TournamentPlayerFilterManager(event).options(),
            'player_filter_options': PlayerFilterOptionManager(event).objects(),
            'containers_by_type': {
                player_filter.id: [
                    option.container_id for option in player_filter.default_options()
                ]
                for player_filter in TournamentPlayerFilterManager(event).objects()
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

        tournament_players = (
            admin_tournament.tournament_players if admin_tournament else None
        )
        random_tournament_player = (
            random.choice(list(tournament_players)) if tournament_players else None
        )

        board: Board | None = None
        if random_tournament_player is not None:
            board = next(
                (
                    b
                    for b in admin_tournament.boards
                    if (
                        b.white_tournament_player is not None
                        and b.white_tournament_player.id == random_tournament_player.id
                    )
                    or (
                        b.black_tournament_player is not None
                        and b.black_tournament_player.id == random_tournament_player.id
                    )
                ),
                None,
            )

        opponent: TournamentPlayer | None = None
        if random_tournament_player and board is not None:
            if (
                board.white_tournament_player
                and board.white_tournament_player.id != random_tournament_player.id
            ):
                opponent = board.white_tournament_player
            elif (
                board.black_tournament_player
                and board.black_tournament_player.id != random_tournament_player.id
            ):
                opponent = board.black_tournament_player

        return HTMXTemplate(
            template_name='admin/tournaments/random_player_modal.html',
            context={
                'player_name': random_tournament_player.full_name
                if random_tournament_player
                else None,
                'random_player': random_tournament_player,
                'opponent_name': opponent.full_name if opponent else None,
                'tournament': admin_tournament,
                'admin_event': admin_event,
                'board': board,
            },
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
        )
