from typing import Annotated, Any

import requests
import validators
from litestar import post, get, delete, patch
from litestar.plugins.htmx import HTMXRequest, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common import REQUEST_TIMEOUT
from common.i18n import _
from data.loader import EventLoader
from data.screen import Screen
from data.screen_set import ScreenSet
from utils.enum import ScreenType
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredScreen, StoredScreenSet
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext, BaseController
from web.messages import Message
from web.session import SessionHandler


class ScreenAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_id: int | None,
        screen_type: str | None,
        screen_set_id: int | None,
        data: Annotated[
            dict[str, Any],
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
        self.admin_screen: Screen | None = None
        self.admin_screen_set: ScreenSet | None = None
        if self.error:
            return
        if screen_id:
            try:
                self.admin_screen = self.admin_event.basic_screens_by_id[screen_id]
            except KeyError:
                self._redirect_error(f'Screen [{screen_id}] not found.')
                return
        self.screen_type = screen_type
        if screen_set_id:
            assert self.admin_screen is not None
            try:
                self.admin_screen_set = self.admin_screen.screen_sets_by_id[
                    screen_set_id
                ]
            except KeyError:
                self._redirect_error(
                    f'Screen set [{screen_set_id}] not found for screen [{self.admin_screen.uniq_id}]'
                )
                return

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_screen': self.admin_screen,
            'screen_type': self.admin_screen.type
            if self.admin_screen
            else self.screen_type,
            'admin_screen_set': self.admin_screen_set,
        }


class ScreenAdminController(BaseEventAdminController):
    @classmethod
    def _admin_validate_screen_update_data(
        cls,
        action: str | None,
        web_context: ScreenAdminWebContext,
        data: dict[str, str] | None = None,
    ) -> StoredScreen:
        assert web_context.admin_event is not None
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
                match type_:
                    case 'boards' | 'input' | 'players' | 'ranking':
                        field = 'init_set_tournament_id'
                        init_set_tournament_id = WebContext.form_data_to_int(
                            data, field
                        )
                        if (
                            init_set_tournament_id
                            not in web_context.admin_event.tournaments_by_id
                        ):
                            errors[field] = _('Please choose the tournament.')
                    case 'results' | 'image':
                        pass
                    case _:
                        raise ValueError(f'type=[{type_}]')
            case 'update' | 'clone' | 'delete':
                assert web_context.admin_screen is not None
                assert web_context.admin_screen.stored_screen is not None
                type_ = web_context.admin_screen.stored_screen.type
            case _:
                raise ValueError(f'action=[{action}]')
        field = 'uniq_id'
        uniq_id: str | None = WebContext.form_data_to_str(data, field)
        name: str | None = None
        public: bool | None = None
        menu_link: bool | None = None
        menu_text: str | None = None
        menu: str | None = None
        columns: int | None = None
        font_size: int | None = None
        timer_id: int | None = None
        input_exit_button: bool | None = None
        players_show_unpaired: bool | None = None
        players_show_opponent: bool | None = None
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
        if action == 'delete':
            pass
        else:
            if not uniq_id:
                errors[field] = _('Please enter the screen ID.')
            elif ':' in uniq_id:
                errors[field] = _('Character [{char}] is not allowed.').format(char=':')
            else:
                match action:
                    case 'create' | 'clone':
                        if uniq_id in web_context.admin_event.screens_by_uniq_id:
                            errors[field] = _(
                                'Screen [{uniq_id}] already exists.'
                            ).format(uniq_id=uniq_id)
                    case 'update':
                        assert web_context.admin_screen is not None
                        if (
                            uniq_id != web_context.admin_screen.uniq_id
                            and uniq_id in web_context.admin_event.screens_by_uniq_id
                        ):
                            errors[field] = _(
                                'Screen [{uniq_id}] already exists.'
                            ).format(uniq_id=uniq_id)
                    case _:
                        raise ValueError(f'action=[{action}]')
        match action:
            case 'create' | 'clone' | 'update':
                name = WebContext.form_data_to_str(data, 'name')
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
                    menu_link = WebContext.form_data_to_bool(data, 'menu_link')
                    menu_text = WebContext.form_data_to_str(data, 'menu_text', '')
                    menu = WebContext.form_data_to_str(data, 'menu', '')
                field = 'timer_id'
                try:
                    timer_id = WebContext.form_data_to_int(data, field)
                    if (
                        timer_id
                        and timer_id not in web_context.admin_event.timers_by_id
                    ):
                        errors[field] = _('Timer [{timer_id}] not found.').format(
                            timer_id=timer_id
                        )
                except ValueError:
                    errors[field] = _('A positive integer is expected.')
                match type_:
                    case ScreenType.BOARDS:
                        pass
                    case ScreenType.INPUT:
                        input_exit_button = WebContext.form_data_to_bool_or_none(
                            data, 'input_exit_button'
                        )
                    case ScreenType.PLAYERS:
                        players_show_unpaired = WebContext.form_data_to_bool_or_none(
                            data, 'players_show_unpaired'
                        )
                        players_show_opponent = WebContext.form_data_to_bool_or_none(
                            data, 'players_show_opponent'
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
                        results_tournament_ids = []
                        for tournament_id in web_context.admin_event.tournaments_by_id:
                            field = f'results_tournament_{tournament_id}'
                            if WebContext.form_data_to_bool(data, field):
                                results_tournament_ids.append(tournament_id)
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
            case 'delete':
                uniq_id = uniq_id or ''
            case _:
                raise ValueError(f'action=[{action}]')

        assert uniq_id is not None

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
            menu_link=menu_link,
            menu_text=menu_text,
            menu=menu,
            timer_id=timer_id,
            input_exit_button=input_exit_button,
            players_show_unpaired=players_show_unpaired,
            players_show_opponent=players_show_opponent,
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

        assert web_context.admin_screen is not None
        assert web_context.admin_screen.event is not None

        try:
            if len(web_context.admin_screen.event.tournaments_by_id) == 1:
                tournament_id = list(
                    web_context.admin_screen.event.tournaments_by_id.keys()
                )[0]
                data[field] = WebContext.value_to_form_data(tournament_id)
            else:
                tournament_id = WebContext.form_data_to_int(data, field)
                if not tournament_id:
                    errors[field] = _('Please choose the tournament.')
                elif (
                    tournament_id
                    not in web_context.admin_screen.event.tournaments_by_id
                ):
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
        if web_context.admin_screen.type in [ScreenType.BOARDS, ScreenType.INPUT]:
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

        assert web_context.admin_screen_set is not None
        assert tournament_id is not None

        return StoredScreenSet(
            id=web_context.admin_screen_set.id,
            screen_id=web_context.admin_screen.id,
            name=name,
            tournament_id=tournament_id,
            order=web_context.admin_screen_set.order,
            fixed_boards_str=fixed_boards_str,
            first=first,
            last=last,
            errors=errors,
        )

    @classmethod
    def _admin_event_screens_render(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        modal: str | None = None,
        action: str | None = None,
        screen_id: int | None = None,
        screen_type: str | None = None,
        screen_set_id: int | None = None,
        data: dict[str, str] | None = None,  # type: ignore
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: ScreenAdminWebContext = ScreenAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            screen_id=screen_id,
            screen_type=screen_type,
            screen_set_id=screen_set_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context
        ) | {
            'admin_event_tab': 'admin-event-screens-tab',
            'admin_screens_show_family_screens': SessionHandler.get_session_admin_screens_show_family_screens(
                web_context.request
            ),
            'admin_screens_show_details': SessionHandler.get_session_admin_screens_show_details(
                web_context.request
            ),
            'admin_screens_screen_types': SessionHandler.get_session_admin_screens_screen_types(
                web_context.request
            ),
        }

        match modal:
            case None:
                pass
            case 'screen':
                if data is None:
                    uniq_id: str | None = None
                    public: bool | None = None
                    name: str | None = None
                    columns: int | None = None
                    font_size: int | None = None
                    menu_link: bool | None = None
                    menu_text: str | None = None
                    menu: str | None = None
                    timer_id: int | None = None
                    background_image: str | None = None
                    background_color: str | None = None
                    message_default: bool | None = None
                    message_text: str | None = None
                    input_exit_button: bool | None = None
                    players_show_unpaired: bool | None = None
                    players_show_opponent: bool | None = None
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
                            assert web_context.admin_screen is not None
                            assert web_context.admin_screen.stored_screen is not None
                            uniq_id = web_context.admin_screen.stored_screen.uniq_id
                            name = web_context.admin_screen.stored_screen.name
                        case 'create':
                            assert screen_type is not None
                            uniq_id = web_context.admin_event.get_unused_screen_uniq_id(
                                screen_type=ScreenType(screen_type)
                            )
                            match screen_type:
                                case 'input' | 'boards' | 'players' | 'ranking':
                                    init_set_tournament_id = list(
                                        web_context.admin_event.tournaments_by_id.keys()
                                    )[0]
                                case 'results' | 'image':
                                    pass
                                case _:
                                    raise ValueError(f'screen_type=[{screen_type}]')
                            name = web_context.admin_event.get_unused_screen_name(
                                screen_type=ScreenType(screen_type)
                            )
                            match screen_type:
                                case 'ranking':
                                    ranking_crosstable = False
                                case (
                                    'input'
                                    | 'boards'
                                    | 'players'
                                    | 'ranking'
                                    | 'results'
                                    | 'image'
                                ):
                                    pass
                                case _:
                                    raise ValueError(f'screen_type=[{screen_type}]')
                        case 'clone':
                            if web_context.admin_screen is None:
                                raise RuntimeError(
                                    f'{web_context.admin_screen=} for [{action=}]'
                                )
                            uniq_id = web_context.admin_event.get_unused_screen_uniq_id(
                                base_uniq_id=web_context.admin_screen.uniq_id
                            )
                            name = web_context.admin_event.get_unused_screen_name(
                                base_name=web_context.admin_screen.name,
                                screen_type=ScreenType(web_context.admin_screen.type),
                            )
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    match action:
                        case 'update' | 'clone':
                            assert web_context.admin_screen is not None
                            assert web_context.admin_screen.stored_screen is not None
                            public = web_context.admin_screen.stored_screen.public
                            columns = web_context.admin_screen.stored_screen.columns
                            font_size = web_context.admin_screen.stored_screen.font_size
                            if web_context.admin_screen.type != ScreenType.IMAGE:
                                menu_link = (
                                    web_context.admin_screen.stored_screen.menu_link
                                )
                                menu_text = (
                                    web_context.admin_screen.stored_screen.menu_text
                                )
                                menu = web_context.admin_screen.stored_screen.menu
                            timer_id = web_context.admin_screen.stored_screen.timer_id
                            match web_context.admin_screen.type:
                                case ScreenType.BOARDS:
                                    pass
                                case ScreenType.INPUT:
                                    input_exit_button = web_context.admin_screen.stored_screen.input_exit_button
                                case ScreenType.PLAYERS:
                                    players_show_unpaired = web_context.admin_screen.stored_screen.players_show_unpaired
                                    players_show_opponent = web_context.admin_screen.stored_screen.players_show_opponent
                                case ScreenType.RESULTS:
                                    results_limit = web_context.admin_screen.stored_screen.results_limit
                                    results_max_age = web_context.admin_screen.stored_screen.results_max_age
                                    results_tournament_ids = web_context.admin_screen.stored_screen.results_tournament_ids
                                case ScreenType.RANKING:
                                    ranking_crosstable = web_context.admin_screen.stored_screen.ranking_crosstable
                                    ranking_round = web_context.admin_screen.stored_screen.ranking_round
                                    ranking_min_points = web_context.admin_screen.stored_screen.ranking_min_points
                                    ranking_max_points = web_context.admin_screen.stored_screen.ranking_max_points
                                case ScreenType.IMAGE:
                                    background_image = web_context.admin_screen.stored_screen.background_image
                                    background_color = (
                                        web_context.admin_screen.background_color
                                    )
                                case _:
                                    raise ValueError(
                                        f'screen_type={web_context.admin_screen.type}'
                                    )
                            message_default = (
                                web_context.admin_screen.stored_screen.message_default
                            )
                            message_text = (
                                web_context.admin_screen.stored_screen.message_text
                            )
                        case 'create':
                            public = True
                            message_default = True
                            if screen_type != ScreenType.IMAGE:
                                menu_link = True
                            match screen_type:
                                case ScreenType.BOARDS:
                                    menu = '@boards'
                                case ScreenType.INPUT:
                                    menu = '@input'
                                case ScreenType.PLAYERS:
                                    menu = '@players'
                                case ScreenType.RANKING:
                                    menu = '@ranking'
                                case ScreenType.RESULTS | ScreenType.IMAGE:
                                    pass
                                case _:
                                    raise ValueError(f'screen_type={screen_type}')
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    data = {
                        'uniq_id': WebContext.value_to_form_data(uniq_id),
                        'public': WebContext.value_to_form_data(public),
                        'name': WebContext.value_to_form_data(name),
                        'columns': WebContext.value_to_form_data(columns),
                        'font_size': WebContext.value_to_form_data(font_size),
                        'menu_link': WebContext.value_to_form_data(menu_link),
                        'menu_text': WebContext.value_to_form_data(menu_text),
                        'menu': WebContext.value_to_form_data(menu),
                        'timer_id': WebContext.value_to_form_data(timer_id),
                        'input_exit_button': WebContext.value_to_form_data(
                            input_exit_button
                        ),
                        'players_show_unpaired': WebContext.value_to_form_data(
                            players_show_unpaired
                        ),
                        'players_show_opponent': WebContext.value_to_form_data(
                            players_show_opponent
                        ),
                        'results_limit': WebContext.value_to_form_data(results_limit),
                        'results_max_age': WebContext.value_to_form_data(
                            results_max_age
                        ),
                        'ranking_crosstable': WebContext.value_to_form_data(
                            ranking_crosstable
                        ),
                        'ranking_round': WebContext.value_to_form_data(ranking_round),
                        'ranking_min_points': WebContext.value_to_form_data(
                            ranking_min_points
                        ),
                        'ranking_max_points': WebContext.value_to_form_data(
                            ranking_max_points
                        ),
                        'background_image': WebContext.value_to_form_data(
                            background_image
                        ),
                        'background_color': WebContext.value_to_form_data(
                            background_color
                        ),
                        'background_color_checkbox': WebContext.value_to_form_data(
                            background_color is None
                        ),
                        'message_text_checkbox': WebContext.value_to_form_data(
                            message_default
                        ),
                        'message_text': WebContext.value_to_form_data(message_text),
                        'init_set_tournament_id': WebContext.value_to_form_data(
                            init_set_tournament_id
                        ),
                    }
                    if results_tournament_ids:
                        data |= {
                            f'results_tournament_{tournament_id}': WebContext.value_to_form_data(
                                tournament_id
                            )
                            for tournament_id in results_tournament_ids
                        }
                stored_screen: StoredScreen = cls._admin_validate_screen_update_data(
                    action, web_context, data
                )
                errors = stored_screen.errors
                if errors is None:
                    errors = {}
                template_context |= {
                    'tournament_options': web_context.get_tournament_options(),
                    'screen_type_options': cls._get_screen_type_options(
                        family_screens_only=False
                    ),
                    'timer_options': cls._get_timer_options(web_context.admin_event),
                    'input_exit_button_options': cls._get_input_exit_button_options(),
                    'players_show_unpaired_options': cls._get_players_show_unpaired_options(),
                    'players_show_opponent_options': cls._get_players_show_opponent_options(),
                    'ranking_crosstable_options': cls._get_ranking_crosstable_options(),
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case 'screen_sets':
                if data is None:
                    if web_context.admin_screen_set:
                        assert web_context.admin_screen is not None
                        assert (
                            web_context.admin_screen_set.stored_screen_set is not None
                        )
                        data = {
                            'tournament_id': WebContext.value_to_form_data(
                                web_context.admin_screen_set.stored_screen_set.tournament_id
                            ),
                            'fixed_boards_str': WebContext.value_to_form_data(
                                web_context.admin_screen_set.stored_screen_set.fixed_boards_str
                            ),
                            'name': WebContext.value_to_form_data(
                                web_context.admin_screen_set.stored_screen_set.name
                            ),
                            'first': WebContext.value_to_form_data(
                                web_context.admin_screen_set.stored_screen_set.first
                            ),
                            'last': WebContext.value_to_form_data(
                                web_context.admin_screen_set.stored_screen_set.last
                            ),
                        }
                        if web_context.admin_screen.type in [
                            ScreenType.BOARDS,
                            ScreenType.INPUT,
                        ]:
                            data['fixed_boards_str'] = WebContext.value_to_form_data(
                                web_context.admin_screen_set.stored_screen_set.fixed_boards_str
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
        return cls._admin_event_render(template_context)

    @get(
        path='/admin/event/{event_uniq_id:str}/screens',
        name='admin-event-screens-tab',
        cache=1,
    )
    async def htmx_admin_event_screens_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        admin_screens_show_family_screens: bool | None,
        admin_screens_show_details: bool | None,
        admin_screens_show_boards: bool | None,
        admin_screens_show_input: bool | None,
        admin_screens_show_players: bool | None,
        admin_screens_show_results: bool | None,
        admin_screens_show_ranking: bool | None,
        admin_screens_show_image: bool | None,
    ) -> Template | ClientRedirect:
        if admin_screens_show_family_screens is not None:
            SessionHandler.set_session_admin_screens_show_family_screens(
                request, admin_screens_show_family_screens
            )
        if admin_screens_show_details is not None:
            SessionHandler.set_session_admin_screens_show_details(
                request, admin_screens_show_details
            )
        screen_types: set[str] = SessionHandler.get_session_admin_screens_screen_types(
            request
        )
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
                SessionHandler.set_session_admin_screens_screen_types(
                    request, screen_types
                )
                continue
        return self._admin_event_screens_render(
            request,
            event_uniq_id=event_uniq_id,
        )

    @get(
        path='/admin/screen-modal/create/{event_uniq_id:str}/{screen_type:str}',
        name='admin-screen-create-modal',
        cache=1,
    )
    async def htmx_admin_screen_create_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_type: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_screens_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='screen',
            action='create',
            screen_id=None,
            screen_type=screen_type,
        )

    @get(
        path='/admin/screen-modal/{action:str}/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-modal',
        cache=1,
    )
    async def htmx_admin_screen_modal(
        self,
        request: HTMXRequest,
        action: str,
        event_uniq_id: str,
        screen_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_screens_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='screen',
            action=action,
            screen_id=screen_id,
        )

    def _admin_screen_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        action: str,
        screen_id: int | None,
        screen_type: str | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        assert screen_id is not None or screen_type is not None
        match action:
            case 'update' | 'delete' | 'clone' | 'create':
                web_context: ScreenAdminWebContext = ScreenAdminWebContext(
                    request,
                    event_uniq_id=event_uniq_id,
                    screen_id=screen_id,
                    screen_type=screen_type,
                    screen_set_id=None,
                    data=data,
                )
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        stored_screen: StoredScreen = self._admin_validate_screen_update_data(
            action, web_context, data
        )
        if stored_screen.errors:
            return self._admin_event_screens_render(
                request,
                event_uniq_id=event_uniq_id,
                modal='screen',
                action=action,
                screen_id=screen_id,
                screen_type=screen_type,
                data=data,
                errors=stored_screen.errors,
            )
        event_loader: EventLoader = EventLoader.get(request=request)
        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
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
                    ]:
                        if init_set_tournament_id is None:
                            raise RuntimeError(
                                'Missing data: not able to create default screen set'
                            )
                        event_database.add_stored_screen_set(
                            stored_screen.id, init_set_tournament_id
                        )
                    event_database.commit()
                    Message.success(
                        request,
                        _('Screen [{screen_uniq_id}] has been created.').format(
                            screen_uniq_id=stored_screen.uniq_id
                        ),
                    )
                case 'clone':
                    assert web_context.admin_screen is not None
                    stored_screen = event_database.add_stored_screen(stored_screen)
                    assert stored_screen.id is not None
                    if stored_screen.type in [
                        ScreenType.BOARDS,
                        ScreenType.INPUT,
                        ScreenType.PLAYERS,
                        ScreenType.RANKING,
                    ]:
                        for (
                            screen_set
                        ) in web_context.admin_screen.screen_sets_sorted_by_order:
                            assert screen_set.id is not None
                            event_database.clone_stored_screen_set(
                                screen_set.id, stored_screen.id
                            )
                    event_database.commit()
                    Message.success(
                        request,
                        _('Screen [{screen_uniq_id}] has been created.').format(
                            screen_uniq_id=stored_screen.uniq_id
                        ),
                    )
                case 'update':
                    stored_screen = event_database.update_stored_screen(stored_screen)
                    event_database.commit()
                    Message.success(
                        request,
                        _('Screen [{screen_uniq_id}] has been updated.').format(
                            screen_uniq_id=stored_screen.uniq_id
                        ),
                    )
                case 'delete':
                    assert web_context.admin_screen is not None
                    event_database.delete_stored_screen(web_context.admin_screen.id)
                    event_database.commit()
                    Message.success(
                        request,
                        _('Screen [{screen_uniq_id}] has been deleted.').format(
                            screen_uniq_id=web_context.admin_screen.uniq_id
                        ),
                    )
                case _:
                    raise ValueError(f'action=[{action}]')
        event_loader.clear_cache(event_uniq_id)
        return self._admin_event_screens_render(request, event_uniq_id=event_uniq_id)

    @post(
        path='/admin/screen-create/{event_uniq_id:str}/{screen_type:str}',
        name='admin-screen-create',
    )
    async def htmx_admin_screen_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        screen_type: str,
    ) -> Template | ClientRedirect:
        return self._admin_screen_update(
            request,
            event_uniq_id=event_uniq_id,
            action='create',
            screen_id=None,
            screen_type=screen_type,
            data=data,
        )

    @post(
        path='/admin/screen-clone/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-clone',
    )
    async def htmx_admin_screen_clone(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_id: int,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_screen_update(
            request,
            event_uniq_id=event_uniq_id,
            action='clone',
            screen_id=screen_id,
            screen_type=None,
            data=data,
        )

    @patch(
        path='/admin/screen-update/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-update',
    )
    async def htmx_admin_screen_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_id: int,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_screen_update(
            request,
            event_uniq_id=event_uniq_id,
            action='update',
            screen_id=screen_id,
            screen_type=None,
            data=data,
        )

    @delete(
        path='/admin/screen-delete/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_screen_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_id: int,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_screen_update(
            request,
            event_uniq_id=event_uniq_id,
            action='delete',
            screen_id=screen_id,
            screen_type=None,
            data=data,
        )

    @get(
        path='/admin/screen-sets-modal/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-sets-modal',
        cache=1,
    )
    async def htmx_admin_screen_sets_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_event_screens_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='screen_sets',
            screen_id=screen_id,
            screen_set_id=None,
        )

    @get(
        path='/admin/screen-sets-set-modal/{event_uniq_id:str}/{screen_id:int}/{screen_set_id:int}',
        name='admin-screen-sets-set-modal',
        cache=1,
    )
    async def htmx_admin_screen_sets_set_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_id: int,
        screen_set_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_event_screens_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='screen_sets',
            screen_id=screen_id,
            screen_set_id=screen_set_id,
        )

    def _admin_screen_sets_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_id: int,
        screen_set_id: int | None,
        action: str,
        data: Annotated[
            dict[str, Any],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        match action:
            case 'delete' | 'clone' | 'update' | 'add' | 'reorder':
                web_context: ScreenAdminWebContext = ScreenAdminWebContext(
                    request,
                    event_uniq_id=event_uniq_id,
                    screen_id=screen_id,
                    screen_type=None,
                    screen_set_id=screen_set_id,
                    data=data,
                )
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        if web_context.admin_screen is None:
            raise RuntimeError('admin_screen not defined')
        event_loader: EventLoader = EventLoader.get(request=request)
        match action:
            case 'delete':
                if len(web_context.admin_screen.screen_sets_sorted_by_order) <= 1:
                    return BaseController.redirect_error(
                        request, _('The last set of a screen can not be deleted.')
                    )
            case 'update' | 'clone' | 'add' | 'reorder':
                pass
            case _:
                raise ValueError(f'action=[{action}]')
        next_screen_set_id: int | None = None
        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
            match action:
                case 'update':
                    stored_screen_set: StoredScreenSet = (
                        self._admin_validate_screen_set_update_data(web_context, data)
                    )
                    if stored_screen_set.errors:
                        return self._admin_event_screens_render(
                            request,
                            event_uniq_id=event_uniq_id,
                            modal='screen_sets',
                            screen_id=screen_id,
                            screen_set_id=screen_set_id,
                            data=data,
                            errors=stored_screen_set.errors,
                        )
                    event_database.update_stored_screen_set(stored_screen_set)
                case 'delete':
                    assert web_context.admin_screen_set is not None
                    assert web_context.admin_screen_set.id is not None
                    event_database.delete_stored_screen_set(
                        web_context.admin_screen_set.id, web_context.admin_screen.id
                    )
                case 'clone':
                    assert web_context.admin_screen_set is not None
                    assert web_context.admin_screen_set.id is not None
                    stored_screen_set = event_database.clone_stored_screen_set(
                        web_context.admin_screen_set.id, web_context.admin_screen.id
                    )
                    next_screen_set_id = stored_screen_set.id
                case 'add':
                    stored_screen_set = event_database.add_stored_screen_set(
                        web_context.admin_screen.id,
                        list(web_context.admin_event.tournaments_by_id.keys())[0],
                    )
                    next_screen_set_id = stored_screen_set.id
                case 'reorder':
                    event_database.reorder_stored_screen_sets(
                        web_context.admin_screen.id, data['item']
                    )
                case _:
                    raise ValueError(f'action=[{action}]')
            event_database.commit()
        event_loader.clear_cache(event_uniq_id)
        return self._admin_event_screens_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='screen_sets',
            screen_id=screen_id,
            screen_set_id=next_screen_set_id,
        )

    @post(
        path='/admin/screen-set-add/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-set-add',
    )
    async def htmx_admin_screen_set_add(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_id: int,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_screen_sets_update(
            request,
            event_uniq_id=event_uniq_id,
            action='add',
            screen_id=screen_id,
            screen_set_id=None,
            data=data,
        )

    @post(
        path='/admin/screen-set-clone/{event_uniq_id:str}/{screen_id:int}/{screen_set_id:int}',
        name='admin-screen-set-clone',
    )
    async def htmx_admin_screen_set_clone(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_id: int,
        screen_set_id: int,
        data: Annotated[
            dict[str, str | list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_screen_sets_update(
            request,
            event_uniq_id=event_uniq_id,
            action='clone',
            screen_id=screen_id,
            screen_set_id=screen_set_id,
            data=data,
        )

    @patch(
        path='/admin/screen-set-update/{event_uniq_id:str}/{screen_id:int}/{screen_set_id:int}',
        name='admin-screen-set-update',
    )
    async def htmx_admin_screen_set_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_id: int,
        screen_set_id: int,
        data: Annotated[
            dict[str, str | list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_screen_sets_update(
            request,
            event_uniq_id=event_uniq_id,
            action='update',
            screen_id=screen_id,
            screen_set_id=screen_set_id,
            data=data,
        )

    @delete(
        path='/admin/screen-set-delete/{event_uniq_id:str}/{screen_id:int}/{screen_set_id:int}',
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
        event_uniq_id: str,
        screen_id: int,
        screen_set_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_screen_sets_update(
            request,
            event_uniq_id=event_uniq_id,
            action='delete',
            screen_id=screen_id,
            screen_set_id=screen_set_id,
            data=data,
        )

    @patch(
        path='/admin/screen-reorder-sets/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-reorder-sets',
    )
    async def htmx_admin_screen_reorder_sets(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_id: int,
        data: Annotated[
            dict[str, str | list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_screen_sets_update(
            request,
            event_uniq_id=event_uniq_id,
            action='reorder',
            screen_id=screen_id,
            screen_set_id=None,
            data=data,
        )
