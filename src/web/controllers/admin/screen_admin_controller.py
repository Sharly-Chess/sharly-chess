from typing import Annotated, Any

import requests
import validators
from litestar import post, get, delete, patch
from litestar.exceptions import NotFoundException, ClientException
from litestar.plugins.htmx import HTMXRequest
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK
from litestar_htmx import HTMXTemplate

from common import REQUEST_TIMEOUT
from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.access_levels.actions import AuthAction
from data.screen import Screen
from data.screen_set import ScreenSet
from utils import Utils
from utils.enum import ScreenType
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredScreen, StoredScreenSet
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.admin.event_admin_controller import Redirect
from web.controllers.base_controller import WebContext
from web.guards import EventGuard, ActionGuard, ManageScreenEntityGuard
from web.messages import Message
from web.session import (
    SessionScreensShowFamilyScreens,
    SessionScreensShowDetails,
    SessionScreensScreenTypes,
)
from web.urls import admin_event_url


class ScreenAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        screen_id: int | None = None,
        screen_type: str | None = None,
        screen_set_id: int | None = None,
        reload_event: bool = False,
    ):
        super().__init__(request, reload_event)
        assert self.admin_event is not None
        self.admin_screen: Screen | None = None
        self.admin_screen_set: ScreenSet | None = None
        if screen_id:
            try:
                self.admin_screen = self.admin_event.basic_screens_by_id[screen_id]
            except KeyError:
                raise NotFoundException(f'Screen [{screen_id}] not found.')

        if screen_set_id:
            assert self.admin_screen is not None
            try:
                self.admin_screen_set = self.admin_screen.screen_sets_by_id[
                    screen_set_id
                ]
            except KeyError:
                raise NotFoundException(
                    f'Screen set [{screen_set_id}] not found for screen [{self.admin_screen.uniq_id}]'
                )

        self.screen_type: ScreenType | None = None
        if self.admin_screen:
            self.screen_type = self.admin_screen.type
        elif screen_type:
            try:
                self.screen_type = ScreenType(screen_type)
            except ValueError:
                raise NotFoundException(f'Unknown screen type [{screen_type}].')

    def get_admin_screen(self) -> Screen:
        assert self.admin_screen is not None
        return self.admin_screen

    def get_admin_screen_set(self) -> ScreenSet:
        assert self.admin_screen_set is not None
        return self.admin_screen_set

    def get_screen_type(self) -> ScreenType:
        assert self.screen_type is not None
        return self.screen_type

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_screen': self.admin_screen,
            'screen_type': self.screen_type,
            'admin_screen_set': self.admin_screen_set,
        }


class ScreenAdminController(BaseEventAdminController):
    guards = [
        EventGuard(),
        ActionGuard(AuthAction.VIEW_PUBLIC_SCREENS),
        ManageScreenEntityGuard('screen_id'),
    ]

    @classmethod
    def _admin_validate_screen_update_data(
        cls,
        action: str | None,
        web_context: ScreenAdminWebContext,
        data: dict[str, str] | None = None,
    ) -> StoredScreen:
        event = web_context.get_admin_event()
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        field: str
        type_: str
        init_set_tournament_id: int | None = None
        match action:
            case 'create':
                assert web_context.screen_type is not None
                type_ = web_context.screen_type
                if not type_.supports_event_type(event.event_type):
                    raise ValueError(
                        f'Screen type [{type_}] is not available for '
                        f'[{event.event_type}] events.'
                    )
                match type_:
                    case (
                        ScreenType.BOARDS
                        | ScreenType.INPUT
                        | ScreenType.PLAYERS
                        | ScreenType.RANKING
                        | ScreenType.CHECK_IN
                    ):
                        field = 'init_set_tournament_id'
                        init_set_tournament_id = WebContext.form_data_to_int(
                            data, field
                        )
                        if init_set_tournament_id not in event.tournaments_by_id:
                            errors[field] = _('Please choose the tournament.')
                    case ScreenType.RESULTS | ScreenType.IMAGE:
                        pass
                    case _:
                        raise ValueError(f'type=[{type_}]')
            case 'update' | 'clone' | 'delete':
                stored_screen = web_context.get_admin_screen().stored_screen
                assert stored_screen is not None
                type_ = stored_screen.type
            case _:
                raise ValueError(f'action=[{action}]')
        name: str | None = None
        public: bool | None = None
        menu_text: str | None = None
        columns: int | None = None
        font_size: int | None = None
        timer_id: int | None = None
        input_exit_button: bool | None = None
        players_show_unpaired: bool | None = None
        players_player_format: int | None = None
        players_board_format: int | None = None
        players_opponent_format: int | None = None
        results_limit: int | None = None
        results_max_age: int | None = None
        results_tournament_ids: list[int] = []
        ranking_crosstable: bool = False
        ranking_round: int | None = None
        ranking_min_points: float | None = None
        ranking_max_points: float | None = None
        background_image: str | None = None
        background_color: str | None = None
        message_default: bool = True
        message_text: str | None = None
        match action:
            case 'create' | 'clone' | 'update':
                name = WebContext.form_data_to_str(data, 'name') or ''
                public = WebContext.form_data_to_bool(data, 'public')
                field = 'columns'
                try:
                    columns = WebContext.form_data_to_int(data, field, minimum=1)
                except ValueError:
                    errors[field] = _('A positive integer is expected.')
                field = 'font_size'
                try:
                    font_size = WebContext.form_data_to_int(data, field, minimum=1)
                except ValueError:
                    errors[field] = _('A positive integer is expected.')
                if type_ != ScreenType.IMAGE:
                    menu_text = WebContext.form_data_to_str(data, 'menu_text', '')
                field = 'timer_id'
                try:
                    timer_id = WebContext.form_data_to_int(data, field)
                    if timer_id and timer_id not in event.timers_by_id:
                        errors[field] = _('Timer [{timer_id}] not found.').format(
                            timer_id=timer_id
                        )
                except ValueError:
                    errors[field] = _('A positive integer is expected.')
                match type_:
                    case ScreenType.BOARDS:
                        pass
                    case ScreenType.INPUT:
                        input_exit_button = WebContext.form_data_to_bool(
                            data, 'input_exit_button'
                        )
                    case ScreenType.CHECK_IN:
                        input_exit_button = WebContext.form_data_to_bool(
                            data, 'input_exit_button'
                        )
                    case ScreenType.PLAYERS:
                        players_show_unpaired = WebContext.form_data_to_bool(
                            data, 'players_show_unpaired'
                        )
                        players_player_format = WebContext.form_data_to_int(
                            data, 'players_player_format'
                        )
                        players_board_format = WebContext.form_data_to_int(
                            data, 'players_board_format'
                        )
                        players_opponent_format = WebContext.form_data_to_int(
                            data, 'players_opponent_format'
                        )
                    case ScreenType.RESULTS:
                        field = 'results_limit'
                        try:
                            results_limit = WebContext.form_data_to_int(data, field)
                        except ValueError:
                            errors[field] = _('A positive integer is expected.')
                        field = 'results_max_age'
                        try:
                            results_max_age = WebContext.form_data_to_int(data, field)
                        except ValueError:
                            errors[field] = _('A positive integer is expected.')
                        results_tournament_ids = [
                            tournament_id
                            for tournament_id in WebContext.form_data_to_list_int(
                                data, 'results_tournament_ids'
                            )
                            if tournament_id in event.tournaments_by_id
                        ]
                    case ScreenType.RANKING:
                        ranking_crosstable = WebContext.form_data_to_bool(
                            data, field := 'ranking_crosstable'
                        )
                        try:
                            ranking_round = WebContext.form_data_to_int(
                                data, field := 'ranking_round'
                            )
                        except ValueError:
                            errors[field] = _('A positive integer is expected.')
                        try:
                            ranking_min_points = WebContext.form_data_to_float(
                                data, field := 'ranking_min_points'
                            )
                        except ValueError:
                            errors[field] = _('A positive integer is expected.')
                        try:
                            ranking_max_points = WebContext.form_data_to_float(
                                data, field := 'ranking_max_points'
                            )
                        except ValueError:
                            errors[field] = _('A positive integer is expected.')
                    case ScreenType.IMAGE:
                        field = 'background_image'
                        background_image = WebContext.form_data_to_str(data, field, '')
                        if not background_image:
                            errors[field] = _('Please enter the image URL.')
                        elif not validators.url(background_image):
                            errors[field] = _(
                                'Invalid URL [{background_image}].'
                            ).format(background_image=background_image)
                        else:
                            try:
                                response = requests.get(
                                    background_image, timeout=REQUEST_TIMEOUT
                                )
                                if response.status_code != 200:
                                    errors[field] = _(
                                        'URL [{url}] responded code [{code}].'
                                    ).format(
                                        url=background_image, code=response.status_code
                                    )
                            except requests.ConnectionError as ce:
                                errors[field] = _(
                                    'URL [{url}] did not respond (error: [{error}]).'
                                ).format(url=background_image, error=str(ce))
                        background_color = (
                            cls._admin_validate_background_color_update_data(
                                data, errors
                            )
                        )
                    case _:
                        raise ValueError(f'type=[{type_}]')
                field = 'message_text'
                message_default = WebContext.form_data_to_bool(
                    data, field + '_checkbox'
                )
                if (
                    message_default
                    and web_context.admin_screen
                    and web_context.admin_screen.stored_screen
                ):
                    # do not change the original value when the default message is used
                    # (needed since disabled fields are not submitted)
                    message_text = web_context.admin_screen.stored_screen.message_text
                else:
                    message_text = WebContext.form_data_to_str(data, field)
                if action == 'update':
                    uniq_id = web_context.get_admin_screen().uniq_id
                else:
                    uniq_id = event.get_unused_screen_uniq_id(
                        ScreenType(type_),
                        Utils.name_to_uniq_id(name) if name else None,
                    )
            case 'delete':
                uniq_id = ''
            case _:
                raise ValueError(f'action=[{action}]')

        screen_id: int | None = None
        if web_context.admin_screen and action not in [
            'create',
            'clone',
        ]:
            screen_id = web_context.admin_screen.id

        return StoredScreen(
            id=screen_id,
            uniq_id=uniq_id,
            type=type_,
            public=bool(public),
            name=name,
            columns=columns,
            font_size=font_size,
            menu_text=menu_text,
            timer_id=timer_id,
            input_exit_button=input_exit_button,
            players_show_unpaired=players_show_unpaired,
            players_player_format=players_player_format,
            players_board_format=players_board_format,
            players_opponent_format=players_opponent_format,
            results_limit=results_limit,
            results_max_age=results_max_age,
            results_tournament_ids=results_tournament_ids,
            ranking_crosstable=ranking_crosstable,
            ranking_round=ranking_round,
            ranking_min_points=ranking_min_points,
            ranking_max_points=ranking_max_points,
            background_image=background_image,
            background_color=background_color,
            message_default=message_default,
            message_text=message_text,
            errors=errors,
            init_set_tournament_id=init_set_tournament_id,
        )

    @staticmethod
    def _admin_validate_screen_set_update_data(
        web_context: ScreenAdminWebContext,
        data: dict[str, str] | None = None,
    ) -> StoredScreenSet:
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        tournament_id: int | None = None
        name: str | None
        first: int | None = None
        last: int | None = None
        field = 'name'
        name = WebContext.form_data_to_str(data, field)
        field = 'tournament_id'

        event = web_context.get_admin_event()
        screen = web_context.get_admin_screen()
        screen_set = web_context.get_admin_screen_set()
        try:
            if len(event.tournaments_by_id) == 1:
                tournament_id = list(event.tournaments_by_id.keys())[0]
                data[field] = WebContext.value_to_form_data(tournament_id)
            else:
                tournament_id = WebContext.form_data_to_int(data, field)
                if not tournament_id:
                    errors[field] = _('Please choose the tournament.')
                elif tournament_id not in event.tournaments_by_id:
                    errors[field] = _('Tournament [{tournament_id}] not found.').format(
                        tournament_id=tournament_id
                    )
        except ValueError:
            errors[field] = _('A positive integer is expected.')
        field = 'first'
        try:
            first = WebContext.form_data_to_int(data, field, minimum=1)
        except ValueError:
            errors[field] = _('A positive integer is expected.')
        field = 'last'
        try:
            last = WebContext.form_data_to_int(data, field, minimum=1)
        except ValueError:
            errors[field] = _('A positive integer is expected.')
        if first and last and first > last:
            error: str = _(
                'Numbers {first} and {last} are not compatible ({first} > {last}).'
            ).format(first=first, last=last)
            errors['first'] = error
            errors['last'] = error
        fixed_boards_str: str | None = None
        if screen.type in [ScreenType.BOARDS, ScreenType.INPUT]:
            fixed_boards_str = WebContext.form_data_to_str(data, 'fixed_boards_str')
            if fixed_boards_str:
                for fixed_board_str in list(
                    map(str.strip, fixed_boards_str.split(','))
                ):
                    if fixed_board_str:
                        try:
                            int(fixed_board_str)
                        except ValueError:
                            errors['fixed_boards_str'] = _(
                                'Invalid board number [{fixed_board_str}].'
                            ).format(fixed_board_str=fixed_board_str)
                            break

        assert tournament_id is not None

        return StoredScreenSet(
            id=screen_set.id,
            screen_id=screen.id,
            name=name,
            tournament_id=tournament_id,
            order=screen_set.order,
            fixed_boards_str=fixed_boards_str,
            first=first,
            last=last,
            errors=errors,
        )

    @classmethod
    def _admin_event_screens_render(
        cls,
        request: HTMXRequest,
        modal: str | None = None,
        action: str | None = None,
        screen_id: int | None = None,
        screen_type: str | None = None,
        screen_set_id: int | None = None,
        reload_event: bool = False,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> HTMXTemplate | Redirect:
        web_context = ScreenAdminWebContext(
            request,
            screen_id=screen_id,
            screen_type=screen_type,
            screen_set_id=screen_set_id,
            reload_event=reload_event,
        )
        event = web_context.get_admin_event()
        admin_screen_types_data: dict[ScreenType, dict[str, Any]] = {
            screen_type: {}
            for screen_type in ScreenType
            if screen_type.supports_event_type(event.event_type)
        }
        template_context: dict[str, Any] = web_context.template_context

        if web_context.client.can_manage_screens:
            # 'admin' view
            show_family_screens = SessionScreensShowFamilyScreens(request).get()
            sorted_screens_by_type: dict[ScreenType, list[Screen]]
            if show_family_screens:
                sorted_screens_by_type = event.sorted_screens_by_screen_type
            else:
                sorted_screens_by_type = event.sorted_basic_screens_by_screen_type
            for screen_type_ in list(admin_screen_types_data):
                screens = sorted_screens_by_type[screen_type_]
                admin_screen_types_data[screen_type_]['screens'] = screens
                admin_screen_types_data[screen_type_]['title'] = (
                    f'{screen_type_.name} ({len(screens) or "-"})'
                )
            template_context |= {
                'admin_event_tab': 'admin-event-screens-tab',
                'admin_screen_types_data': admin_screen_types_data,
                'show_family_screens': show_family_screens,
                'show_details': SessionScreensShowDetails(request).get(),
                'admin_screens_screen_types': SessionScreensScreenTypes(request).get(),
                'admin_screens_count': sum(
                    len(admin_screen_types_data[ScreenType(screen_type)])
                    for screen_type in admin_screen_types_data
                ),
            }
        else:
            # 'user' view
            screen_type = web_context.get_screen_type()
            if web_context.client.can_view_private_screens:
                sorted_screens = event.sorted_screens_by_screen_type[screen_type]
            else:
                sorted_screens = event.sorted_public_screens_by_screen_type[screen_type]
            if not sorted_screens:
                return Redirect(admin_event_url(request, event_uniq_id=event.uniq_id))

            # setdefault: legacy screens of a type no longer offered for
            # the event's type still render rather than crash.
            admin_screen_type_data = admin_screen_types_data.setdefault(screen_type, {})
            admin_screen_type_data['screens'] = sorted_screens
            admin_screen_type_data['title'] = (
                f'{screen_type.name} ({len(sorted_screens) or "-"})'
            )

            template_context |= {
                'admin_event_tab': f'admin-event-{screen_type.value}-screens-tab',
                'admin_screen_type_data': admin_screen_type_data,
                'admin_screens_count': len(admin_screen_type_data['screens']),
            }

        match modal:
            case None:
                pass
            case 'screen':
                if data is None:
                    public: bool | None = None
                    name: str | None = None
                    columns: int | None = None
                    font_size: int | None = None
                    menu_text: str | None = None
                    timer_id: int | None = None
                    background_image: str | None = None
                    background_color: str | None = None
                    message_default: bool | None = None
                    message_text: str | None = None
                    input_exit_button: bool | None = None
                    players_show_unpaired: bool = True
                    players_player_format: int | None = None
                    players_board_format: int | None = None
                    players_opponent_format: int | None = None
                    results_limit: int | None = None
                    results_max_age: int | None = None
                    results_tournament_ids: list[int] | None = None
                    ranking_crosstable: bool = False
                    ranking_round: int | None = None
                    ranking_min_points: float | None = None
                    ranking_max_points: float | None = None
                    init_set_tournament_id: int | None = None
                    match action:
                        case 'update':
                            stored_screen = web_context.get_admin_screen().stored_screen
                            assert stored_screen is not None
                            name = stored_screen.name
                        case 'create':
                            screen_type = web_context.get_screen_type()
                            match screen_type:
                                case (
                                    ScreenType.INPUT
                                    | ScreenType.BOARDS
                                    | ScreenType.PLAYERS
                                    | ScreenType.RANKING
                                    | ScreenType.CHECK_IN
                                ):
                                    init_set_tournament_id = list(
                                        event.tournaments_by_id.keys()
                                    )[0]
                                case ScreenType.RESULTS | ScreenType.IMAGE:
                                    pass
                                case _:
                                    raise ValueError(f'screen_type=[{screen_type}]')
                            # No default name: an unnamed screen is named
                            # automatically from its tournament(s).
                            if ScreenType.RANKING:
                                ranking_crosstable = False
                        case 'clone':
                            screen = web_context.get_admin_screen()
                            name = event.get_unused_screen_name(
                                base_name=screen.name,
                                screen_type=ScreenType(screen.type),
                            )
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    match action:
                        case 'update' | 'clone':
                            screen = web_context.get_admin_screen()
                            stored_screen = screen.stored_screen
                            assert stored_screen is not None
                            public = stored_screen.public
                            columns = stored_screen.columns
                            font_size = stored_screen.font_size
                            if screen.type != ScreenType.IMAGE:
                                menu_text = stored_screen.menu_text
                            timer_id = stored_screen.timer_id
                            match screen.type:
                                case ScreenType.BOARDS:
                                    pass
                                case ScreenType.CHECK_IN:
                                    input_exit_button = stored_screen.input_exit_button
                                case ScreenType.INPUT:
                                    input_exit_button = stored_screen.input_exit_button
                                case ScreenType.PLAYERS:
                                    players_show_unpaired = (
                                        stored_screen.players_show_unpaired or False
                                    )
                                    players_player_format = (
                                        stored_screen.players_player_format
                                    )
                                    players_board_format = (
                                        stored_screen.players_board_format
                                    )
                                    players_opponent_format = (
                                        stored_screen.players_opponent_format
                                    )
                                case ScreenType.RESULTS:
                                    results_limit = stored_screen.results_limit
                                    results_max_age = stored_screen.results_max_age
                                    results_tournament_ids = (
                                        stored_screen.results_tournament_ids
                                    )
                                case ScreenType.RANKING:
                                    ranking_crosstable = (
                                        stored_screen.ranking_crosstable
                                    )
                                    ranking_round = stored_screen.ranking_round
                                    ranking_min_points = (
                                        stored_screen.ranking_min_points
                                    )
                                    ranking_max_points = (
                                        stored_screen.ranking_max_points
                                    )
                                case ScreenType.IMAGE:
                                    background_image = stored_screen.background_image
                                    background_color = screen.background_color
                                case _:
                                    raise ValueError(f'screen_type={screen.type}')
                            message_default = stored_screen.message_default
                            message_text = stored_screen.message_text
                        case 'create':
                            public = True
                            message_default = True
                            match web_context.screen_type:
                                case (
                                    ScreenType.BOARDS
                                    | ScreenType.INPUT
                                    | ScreenType.CHECK_IN
                                    | ScreenType.RANKING
                                    | ScreenType.RESULTS
                                    | ScreenType.IMAGE
                                ):
                                    pass
                                case ScreenType.PLAYERS:
                                    columns = cls.get_default_players_screen_columns(
                                        event
                                    )
                                    players_player_format = (
                                        cls.get_default_players_screen_player_format(
                                            event
                                        ).value
                                    )
                                    players_board_format = (
                                        cls.get_default_players_screen_board_format(
                                            event
                                        ).value
                                    )
                                    players_opponent_format = (
                                        cls.get_default_players_screen_opponent_format(
                                            event
                                        ).value
                                    )
                                case _:
                                    raise ValueError(
                                        f'screen_type={web_context.screen_type}'
                                    )
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    data = WebContext.values_dict_to_form_data(
                        {
                            'public': public,
                            'name': name,
                            'columns': columns,
                            'font_size': font_size,
                            'menu_text': menu_text,
                            'timer_id': timer_id,
                            'input_exit_button': input_exit_button,
                            'players_show_unpaired': players_show_unpaired,
                            'players_player_format': players_player_format,
                            'players_board_format': players_board_format,
                            'players_opponent_format': players_opponent_format,
                            'results_limit': results_limit,
                            'results_max_age': results_max_age,
                            'ranking_crosstable': ranking_crosstable,
                            'ranking_round': ranking_round,
                            'ranking_min_points': ranking_min_points,
                            'ranking_max_points': ranking_max_points,
                            'background_image': background_image,
                            'background_color': background_color,
                            'background_color_checkbox': background_color is None,
                            'message_text_checkbox': message_default,
                            'message_text': message_text,
                            'init_set_tournament_id': init_set_tournament_id,
                            'results_tournament_ids': results_tournament_ids,
                        }
                    )
                stored_screen = cls._admin_validate_screen_update_data(
                    action, web_context, data
                )
                assert stored_screen is not None
                errors = stored_screen.errors
                if errors is None:
                    errors = {}
                template_context |= {
                    'tournament_options': web_context.get_tournament_options(),
                    'screen_type_options': cls._get_screen_type_options(
                        family_screens_only=False, event=event
                    ),
                    'timer_options': cls._get_timer_options(event),
                    'ranking_crosstable_options': cls._get_ranking_crosstable_options(),
                    'screen_uniq_ids': list(event.screens_by_uniq_id.keys()),
                    'players_player_format_options': web_context.get_players_screen_player_format_options(),
                    'players_board_format_options': web_context.get_players_screen_board_format_options(),
                    'players_opponent_format_options': web_context.get_players_screen_opponent_format_options(),
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case 'screen_sets':
                if data is None:
                    if web_context.admin_screen_set:
                        stored_screen_set = (
                            web_context.admin_screen_set.stored_screen_set
                        )
                        assert stored_screen_set is not None
                        data = {
                            'tournament_id': WebContext.value_to_form_data(
                                stored_screen_set.tournament_id
                            ),
                            'fixed_boards_str': WebContext.value_to_form_data(
                                stored_screen_set.fixed_boards_str
                            ),
                            'name': WebContext.value_to_form_data(
                                stored_screen_set.name
                            ),
                            'first': WebContext.value_to_form_data(
                                stored_screen_set.first
                            ),
                            'last': WebContext.value_to_form_data(
                                stored_screen_set.last
                            ),
                        }
                        screen = web_context.get_admin_screen()
                        if screen.type in [
                            ScreenType.BOARDS,
                            ScreenType.INPUT,
                        ]:
                            data['fixed_boards_str'] = WebContext.value_to_form_data(
                                stored_screen_set.fixed_boards_str
                            )
                        stored_screen_set = cls._admin_validate_screen_set_update_data(
                            web_context, data
                        )
                        errors = stored_screen_set.errors
                    else:
                        data = {}
                if errors is None:
                    errors = {}
                template_context |= {
                    'tournament_options': web_context.get_tournament_options(),
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case _:
                raise ValueError(f'modal=[{modal}]')
        return cls._admin_base_event_render(template_context)

    @get(
        path='/event/{event_uniq_id:str}/screens',
        name='admin-event-screens-tab',
    )
    async def htmx_admin_event_screens_tab(
        self,
        request: HTMXRequest,
        show_family_screens: bool | None,
        show_details: bool | None,
        admin_screens_show_boards: bool | None,
        admin_screens_show_input: bool | None,
        admin_screens_show_players: bool | None,
        admin_screens_show_results: bool | None,
        admin_screens_show_ranking: bool | None,
        admin_screens_show_image: bool | None,
    ) -> Template | Redirect:
        if show_family_screens is not None:
            SessionScreensShowFamilyScreens(request).set(show_family_screens)
        if show_details is not None:
            SessionScreensShowDetails(request).set(show_details)
        screen_types = SessionScreensScreenTypes(request).get()
        for screen_type, param in {
            'boards': admin_screens_show_boards,
            'input': admin_screens_show_input,
            'players': admin_screens_show_players,
            'results': admin_screens_show_results,
            'ranking': admin_screens_show_ranking,
            'image': admin_screens_show_image,
        }.items():
            if param is not None:
                if param:
                    screen_types.add(screen_type)
                else:
                    try:
                        screen_types.remove(screen_type)
                    except KeyError:
                        pass
                SessionScreensScreenTypes(request).set(screen_types)
                continue
        return self._admin_event_screens_render(request)

    @get(
        path='/screen-modal/create/{event_uniq_id:str}/{screen_type:str}',
        name='admin-screen-create-modal',
    )
    async def htmx_admin_screen_create_modal(
        self,
        request: HTMXRequest,
        screen_type: str,
    ) -> Template | Redirect:
        return self._admin_event_screens_render(
            request,
            modal='screen',
            action='create',
            screen_id=None,
            screen_type=screen_type,
        )

    @get(
        path='/screen-modal/{action:str}/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-modal',
    )
    async def htmx_admin_screen_modal(
        self,
        request: HTMXRequest,
        action: str,
        screen_id: int | None,
    ) -> Template | Redirect:
        return self._admin_event_screens_render(
            request,
            modal='screen',
            action=action,
            screen_id=screen_id,
        )

    def _admin_screen_update(
        self,
        request: HTMXRequest,
        action: str,
        screen_id: int | None,
        screen_type: str | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | Redirect:
        assert screen_id is not None or screen_type is not None
        match action:
            case 'update' | 'delete' | 'clone' | 'create':
                web_context = ScreenAdminWebContext(
                    request,
                    screen_id=screen_id,
                    screen_type=screen_type,
                )
            case _:
                raise ValueError(f'action=[{action}]')

        event = web_context.get_admin_event()
        stored_screen: StoredScreen = self._admin_validate_screen_update_data(
            action, web_context, data
        )
        if stored_screen.errors:
            return self._admin_event_screens_render(
                request,
                modal='screen',
                action=action,
                screen_id=screen_id,
                screen_type=screen_type,
                data=data,
                errors=stored_screen.errors,
            )
        with EventDatabase(event.uniq_id, write=True) as event_database:
            match action:
                case 'create':
                    # init_set_tournament_id is the id of the tournament that should be
                    # used to create the default screen_set.
                    # It is set in the screen creation form.
                    # It needs to be saved because EventDatabase.add_stored_screen()
                    # doesn't save it (it is not stored in the database).
                    init_set_tournament_id: int | None = (
                        stored_screen.init_set_tournament_id
                    )
                    stored_screen = event_database.add_stored_screen(stored_screen)
                    assert stored_screen.id is not None
                    if stored_screen.type in [
                        ScreenType.BOARDS,
                        ScreenType.INPUT,
                        ScreenType.PLAYERS,
                        ScreenType.RANKING,
                        ScreenType.CHECK_IN,
                    ]:
                        if init_set_tournament_id is None:
                            raise RuntimeError(
                                'Missing data: not able to create default screen set'
                            )
                        event_database.add_stored_screen_set(
                            stored_screen.id, init_set_tournament_id
                        )
                    Message.success(
                        request,
                        _('Screen [{screen_uniq_id}] has been created.').format(
                            screen_uniq_id=stored_screen.uniq_id
                        ),
                    )
                case 'clone':
                    screen = web_context.get_admin_screen()
                    stored_screen = event_database.add_stored_screen(stored_screen)
                    assert stored_screen.id is not None
                    if stored_screen.type in [
                        ScreenType.BOARDS,
                        ScreenType.INPUT,
                        ScreenType.PLAYERS,
                        ScreenType.RANKING,
                        ScreenType.CHECK_IN,
                    ]:
                        for screen_set in screen.sorted_screen_sets:
                            assert screen_set.id is not None
                            event_database.clone_stored_screen_set(
                                screen_set.id, stored_screen.id
                            )
                    Message.success(
                        request,
                        _('Screen [{screen_uniq_id}] has been created.').format(
                            screen_uniq_id=stored_screen.uniq_id
                        ),
                    )
                case 'update':
                    stored_screen = event_database.update_stored_screen(stored_screen)
                    Message.success(
                        request,
                        _('Screen [{screen_uniq_id}] has been updated.').format(
                            screen_uniq_id=stored_screen.uniq_id
                        ),
                    )
                case 'delete':
                    screen = web_context.get_admin_screen()
                    event_database.delete_stored_screen(screen.id)
                    Message.success(
                        request,
                        _('Screen [{screen_uniq_id}] has been deleted.').format(
                            screen_uniq_id=screen.uniq_id
                        ),
                    )
                case _:
                    raise ValueError(f'action=[{action}]')

        return self._admin_event_screens_render(request, reload_event=True)

    @post(
        path='/screen-create/{event_uniq_id:str}/{screen_type:str}',
        name='admin-screen-create',
        guards=[ActionGuard(AuthAction.MANAGE_SCREENS)],
    )
    async def htmx_admin_screen_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        screen_type: str,
    ) -> Template | Redirect:
        return self._admin_screen_update(
            request,
            action='create',
            screen_id=None,
            screen_type=screen_type,
            data=WebContext.flatten_list_data(data),
        )

    @post(
        path='/screen-clone/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-clone',
    )
    async def htmx_admin_screen_clone(
        self,
        request: HTMXRequest,
        screen_id: int,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | Redirect:
        return self._admin_screen_update(
            request,
            action='clone',
            screen_id=screen_id,
            screen_type=None,
            data=WebContext.flatten_list_data(data),
        )

    @patch(
        path='/screen-update/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-update',
    )
    async def htmx_admin_screen_update(
        self,
        request: HTMXRequest,
        screen_id: int,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | Redirect:
        return self._admin_screen_update(
            request,
            action='update',
            screen_id=screen_id,
            screen_type=None,
            data=WebContext.flatten_list_data(data),
        )

    @patch(
        path='/screen-uniq-id-update/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-uniq-id-update',
    )
    async def htmx_admin_screen_uniq_id_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        screen_id: int,
    ) -> HTMXTemplate:
        web_context = ScreenAdminWebContext(request, screen_id)
        event = web_context.get_admin_event()
        screen = web_context.get_admin_screen()
        new_uniq_id = WebContext.form_data_to_str(data, 'uniq_id')
        if (
            not new_uniq_id
            or not SharlyChessConfig.uniq_id_regex.match(new_uniq_id)
            or (
                new_uniq_id != screen.uniq_id
                and new_uniq_id in event.screens_by_uniq_id.keys()
            )
        ):
            # No precise error (validated in JS)
            raise ClientException(f'Invalid uniq ID [{new_uniq_id}].')
        stored_screen = screen.stored_screen
        assert stored_screen is not None
        stored_screen.uniq_id = new_uniq_id
        with EventDatabase(event.uniq_id, True) as database:
            database.update_stored_screen(stored_screen)

        web_context = ScreenAdminWebContext(request, screen_id, reload_event=True)
        event = web_context.get_admin_event()
        return HTMXTemplate(
            template_name='/admin/screens/screen_update_modal_header.html',
            context=web_context.template_context
            | {'screen_uniq_ids': list(event.screens_by_uniq_id.keys())},
            re_swap='innerHTML',
            re_target='.modal-header',
        )

    @delete(
        path='/screen-delete/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_screen_delete(
        self,
        request: HTMXRequest,
        screen_id: int,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | Redirect:
        return self._admin_screen_update(
            request,
            action='delete',
            screen_id=screen_id,
            screen_type=None,
            data=data,
        )

    @get(
        path='/screen-sets-modal/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-sets-modal',
    )
    async def htmx_admin_screen_sets_modal(
        self,
        request: HTMXRequest,
        screen_id: int,
    ) -> Template | Redirect:
        return self._admin_event_screens_render(
            request,
            modal='screen_sets',
            screen_id=screen_id,
            screen_set_id=None,
        )

    @get(
        path='/screen-sets-set-modal/{event_uniq_id:str}/{screen_id:int}/{screen_set_id:int}',
        name='admin-screen-sets-set-modal',
    )
    async def htmx_admin_screen_sets_set_modal(
        self,
        request: HTMXRequest,
        screen_id: int,
        screen_set_id: int,
    ) -> Template | Redirect:
        return self._admin_event_screens_render(
            request,
            modal='screen_sets',
            screen_id=screen_id,
            screen_set_id=screen_set_id,
        )

    def _admin_screen_sets_update(
        self,
        request: HTMXRequest,
        screen_id: int,
        screen_set_id: int | None,
        action: str,
        data: Annotated[
            dict[str, Any],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | Redirect:
        match action:
            case 'delete' | 'clone' | 'update' | 'add' | 'reorder':
                web_context: ScreenAdminWebContext = ScreenAdminWebContext(
                    request,
                    screen_id=screen_id,
                    screen_set_id=screen_set_id,
                )
            case _:
                raise ValueError(f'action=[{action}]')
        event = web_context.get_admin_event()
        screen = web_context.get_admin_screen()
        match action:
            case 'delete':
                if len(screen.sorted_screen_sets) <= 1:
                    raise ClientException(
                        'The last set of a screen can not be deleted.'
                    )
            case 'update' | 'clone' | 'add' | 'reorder':
                pass
            case _:
                raise ValueError(f'action=[{action}]')
        next_screen_set_id: int | None = None
        with EventDatabase(event.uniq_id, write=True) as event_database:
            match action:
                case 'update':
                    stored_screen_set: StoredScreenSet = (
                        self._admin_validate_screen_set_update_data(web_context, data)
                    )
                    if stored_screen_set.errors:
                        return self._admin_event_screens_render(
                            request,
                            modal='screen_sets',
                            screen_id=screen_id,
                            screen_set_id=screen_set_id,
                            data=data,
                            errors=stored_screen_set.errors,
                        )
                    event_database.update_stored_screen_set(stored_screen_set)
                case 'delete':
                    screen_set = web_context.get_admin_screen_set()
                    assert screen_set.id is not None
                    event_database.delete_stored_screen_set(screen_set.id, screen.id)
                case 'clone':
                    screen_set = web_context.get_admin_screen_set()
                    assert screen_set.id is not None
                    stored_screen_set = event_database.clone_stored_screen_set(
                        screen_set.id, screen.id
                    )
                    next_screen_set_id = stored_screen_set.id
                case 'add':
                    stored_screen_set = event_database.add_stored_screen_set(
                        screen.id, list(event.tournaments_by_id.keys())[0]
                    )
                    next_screen_set_id = stored_screen_set.id
                case 'reorder':
                    event_database.reorder_stored_screen_sets(screen.id, data['item'])
                case _:
                    raise ValueError(f'action=[{action}]')

        return self._admin_event_screens_render(
            request,
            modal='screen_sets',
            screen_id=screen_id,
            screen_set_id=next_screen_set_id,
            reload_event=True,
        )

    @post(
        path='/screen-set-add/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-set-add',
    )
    async def htmx_admin_screen_set_add(
        self,
        request: HTMXRequest,
        screen_id: int,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | Redirect:
        return self._admin_screen_sets_update(
            request,
            action='add',
            screen_id=screen_id,
            screen_set_id=None,
            data=data,
        )

    @post(
        path='/screen-set-clone/{event_uniq_id:str}/{screen_id:int}/{screen_set_id:int}',
        name='admin-screen-set-clone',
    )
    async def htmx_admin_screen_set_clone(
        self,
        request: HTMXRequest,
        screen_id: int,
        screen_set_id: int,
        data: Annotated[
            dict[str, str | list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | Redirect:
        return self._admin_screen_sets_update(
            request,
            action='clone',
            screen_id=screen_id,
            screen_set_id=screen_set_id,
            data=data,
        )

    @patch(
        path='/screen-set-update/{event_uniq_id:str}/{screen_id:int}/{screen_set_id:int}',
        name='admin-screen-set-update',
    )
    async def htmx_admin_screen_set_update(
        self,
        request: HTMXRequest,
        screen_id: int,
        screen_set_id: int,
        data: Annotated[
            dict[str, str | list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | Redirect:
        return self._admin_screen_sets_update(
            request,
            action='update',
            screen_id=screen_id,
            screen_set_id=screen_set_id,
            data=data,
        )

    @delete(
        path='/screen-set-delete/{event_uniq_id:str}/{screen_id:int}/{screen_set_id:int}',
        name='admin-screen-set-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_screen_set_delete(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        screen_id: int,
        screen_set_id: int,
    ) -> Template | Redirect:
        return self._admin_screen_sets_update(
            request,
            action='delete',
            screen_id=screen_id,
            screen_set_id=screen_set_id,
            data=data,
        )

    @patch(
        path='/screen-reorder-sets/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-reorder-sets',
    )
    async def htmx_admin_screen_reorder_sets(
        self,
        request: HTMXRequest,
        screen_id: int,
        data: Annotated[
            dict[str, str | list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | Redirect:
        return self._admin_screen_sets_update(
            request,
            action='reorder',
            screen_id=screen_id,
            screen_set_id=None,
            data=data,
        )

    @get(
        path='/event/{event_uniq_id:str}/input-screens',
        name='admin-event-input-screens-tab',
    )
    async def htmx_admin_event_input_screens_tab(
        self, request: HTMXRequest
    ) -> Template | Redirect:
        return self._admin_event_screens_render(request, screen_type='input')

    @get(
        path='/event/{event_uniq_id:str}/check-in-screens',
        name='admin-event-check-in-screens-tab',
    )
    async def htmx_admin_event_check_in_screens_tab(
        self, request: HTMXRequest
    ) -> Template | Redirect:
        return self._admin_event_screens_render(request, screen_type='check-in')

    @get(
        path='/event/{event_uniq_id:str}/boards-screens',
        name='admin-event-boards-screens-tab',
    )
    async def htmx_admin_event_boards_screens_tab(
        self, request: HTMXRequest
    ) -> Template | Redirect:
        return self._admin_event_screens_render(request, screen_type='boards')

    @get(
        path='/event/{event_uniq_id:str}/players-screens',
        name='admin-event-players-screens-tab',
    )
    async def htmx_admin_event_players_screens_tab(
        self, request: HTMXRequest
    ) -> Template | Redirect:
        return self._admin_event_screens_render(request, screen_type='players')

    @get(
        path='/event/{event_uniq_id:str}/results-screens',
        name='admin-event-results-screens-tab',
    )
    async def htmx_admin_event_results_screens_tab(
        self, request: HTMXRequest
    ) -> Template | Redirect:
        return self._admin_event_screens_render(request, screen_type='results')

    @get(
        path='/event/{event_uniq_id:str}/ranking-screens',
        name='admin-event-ranking-screens-tab',
    )
    async def htmx_admin_event_ranking_screens_tab(
        self, request: HTMXRequest
    ) -> Template | Redirect:
        return self._admin_event_screens_render(request, screen_type='ranking')

    @get(
        path='/event/{event_uniq_id:str}/image-screens',
        name='admin-event-image-screens-tab',
    )
    async def htmx_admin_event_image_screens_tab(
        self, request: HTMXRequest
    ) -> Template | Redirect:
        return self._admin_event_screens_render(request, screen_type='image')
