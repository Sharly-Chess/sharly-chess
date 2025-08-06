from typing import Annotated, Any

from litestar import post, get, patch, delete
from litestar.plugins.htmx import HTMXRequest, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common.i18n import _
from data.family import Family
from data.loader import EventLoader
from utils.enum import ScreenType
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredFamily
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.messages import Message
from web.session import SessionHandler


class FamilyAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        family_id: int | None,
        family_type: str | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ]
        | None,
    ):
        super().__init__(
            request,
            data=data,
            event_uniq_id=event_uniq_id,
        )
        if self.admin_event is None:
            raise RuntimeError('admin_event not defined')
        self.admin_family: Family | None = None
        if self.error:
            return
        if family_id:
            try:
                self.admin_family = self.admin_event.families_by_id[family_id]
            except KeyError:
                self._redirect_error(f'Family [{family_id}] not found.')
                return
        self.family_type = family_type

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_family': self.admin_family,
            'family_type': self.admin_family.type
            if self.admin_family
            else self.family_type,
        }


class FamilyAdminController(BaseEventAdminController):
    @staticmethod
    def _admin_validate_family_update_data(
        action: str,
        web_context: FamilyAdminWebContext,
        data: dict[str, str] | None = None,
    ) -> StoredFamily:
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        field: str
        type_: str
        match action:
            case 'create':
                type_ = web_context.family_type
            case 'update' | 'clone' | 'delete':
                if web_context.admin_family is None:
                    raise RuntimeError(f'{web_context.admin_family=} for [{action=}]')
                type_ = web_context.admin_family.stored_family.type
            case _:
                raise ValueError(f'action=[{action}]')
        match type_:
            case 'boards' | 'input' | 'players' | 'ranking':
                pass
            case _:
                raise ValueError(f'type=[{type_}]')
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
        ranking_crosstable: bool = False
        ranking_round: int | None = None
        ranking_min_points: float | None = None
        ranking_max_points: float | None = None
        tournament_id: int | None = None
        first: int | None = None
        last: int | None = None
        parts: int | None = None
        number: int | None = None
        message_default: bool = True
        message_text: str | None = None
        if action in [
            'delete',
        ]:
            pass
        else:
            if not uniq_id:
                errors[field] = _('Please enter the family ID.')
            elif ':' in uniq_id:
                errors[field] = _('Character [{char}] is not allowed.').format(char=':')
            else:
                match action:
                    case 'create' | 'clone':
                        if web_context.admin_event is None:
                            raise RuntimeError(
                                f'{web_context.admin_event=} for [{action=}]'
                            )
                        if uniq_id in web_context.admin_event.families_by_uniq_id:
                            errors[field] = _(
                                'Family [{uniq_id}] already exists.'
                            ).format(uniq_id=uniq_id)
                    case 'update':
                        if web_context.admin_family is None:
                            raise RuntimeError(
                                f'{web_context.admin_family=} for [{action=}]'
                            )
                        if web_context.admin_event is None:
                            raise RuntimeError(
                                f'{web_context.admin_event=} for [{action=}]'
                            )
                        if (
                            uniq_id != web_context.admin_family.uniq_id
                            and uniq_id in web_context.admin_event.families_by_uniq_id
                        ):
                            errors[field] = _(
                                'Family [{uniq_id}] already exists.'
                            ).format(uniq_id=uniq_id)
                    case _:
                        raise ValueError(f'action=[{action}]')
            name = WebContext.form_data_to_str(data, 'name')
            public = WebContext.form_data_to_bool(data, 'public')
        match action:
            case 'create' | 'clone' | 'update':
                field = 'tournament_id'
                if web_context.admin_event is None:
                    raise RuntimeError(f'{web_context.admin_event=} for [{action=}]')
                try:
                    if len(web_context.admin_event.tournaments_by_id) == 1:
                        tournament_id = list(
                            web_context.admin_event.tournaments_by_id.keys()
                        )[0]
                        data[field] = WebContext.value_to_form_data(tournament_id)
                    else:
                        tournament_id = WebContext.form_data_to_int(data, field)
                        if not tournament_id:
                            errors[field] = _('Please choose the tournament.')
                        elif (
                            tournament_id
                            not in web_context.admin_event.tournaments_by_id
                        ):
                            errors[field] = _(
                                'Tournament [{tournament_id}] not found.'
                            ).format(tournament_id=tournament_id)
                except ValueError:
                    errors[field] = _('A positive integer is expected.')
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
                match type_:
                    case 'boards':
                        pass
                    case 'input':
                        input_exit_button = WebContext.form_data_to_bool_or_none(
                            data, 'input_exit_button'
                        )
                    case 'players':
                        players_show_unpaired = WebContext.form_data_to_bool_or_none(
                            data, 'players_show_unpaired'
                        )
                        players_show_opponent = WebContext.form_data_to_bool_or_none(
                            data, 'players_show_opponent'
                        )
                    case 'ranking':
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
                    case _:
                        raise ValueError(f'type=[{type_}]')
                field = 'parts'
                try:
                    parts = WebContext.form_data_to_int(data, field, minimum=1)
                except ValueError:
                    errors[field] = _('A positive integer is expected.')
                field = 'number'
                try:
                    number = WebContext.form_data_to_int(data, field, minimum=1)
                except ValueError:
                    errors[field] = _('A positive integer is expected.')
                if parts and number:
                    error = _(
                        'Specifying the number of parts and the number of items per part is not possible.'
                    )
                    errors['parts'] = error
                    errors['number'] = error
                field = 'message_text'
                message_default = WebContext.form_data_to_bool(
                    data, field + '_checkbox'
                )
                if message_default and web_context.admin_family:
                    # do not change the original value when the default message is used
                    # (needed since disabled fields are not submitted)
                    message_text = web_context.admin_family.stored_family.message_text
                else:
                    message_text = WebContext.form_data_to_str(data, field)
            case 'delete':
                if web_context.admin_family is None:
                    raise RuntimeError(f'{web_context.admin_family=} for [{action=}]')
                uniq_id = uniq_id or ''
                tournament_id = web_context.admin_family.stored_family.tournament_id
                name = web_context.admin_family.stored_family.name
            case _:
                raise ValueError(f'action=[{action}]')

        assert tournament_id is not None
        assert uniq_id is not None

        family_id: int | None = None
        if web_context.admin_family and action not in [
            'create',
            'clone',
        ]:
            family_id = web_context.admin_family.id

        return StoredFamily(
            id=family_id,
            uniq_id=uniq_id,
            type=type_,
            public=bool(public),
            tournament_id=tournament_id,
            name=name,
            columns=columns,
            font_size=font_size,
            menu_link=bool(menu_link),
            menu_text=menu_text or '',
            menu=menu or '',
            timer_id=timer_id,
            input_exit_button=input_exit_button,
            players_show_unpaired=players_show_unpaired,
            players_show_opponent=players_show_opponent,
            ranking_crosstable=ranking_crosstable,
            ranking_round=ranking_round,
            ranking_min_points=ranking_min_points,
            ranking_max_points=ranking_max_points,
            first=first,
            last=last,
            parts=parts,
            number=number,
            message_default=message_default,
            message_text=message_text,
            errors=errors,
        )

    @classmethod
    def _admin_event_families_render(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        modal: str | None = None,
        action: str | None = None,
        family_id: int | None = None,
        family_type: str | None = None,
        data: dict[str, str] | None = None,  # type: ignore
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: FamilyAdminWebContext = FamilyAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            family_id=family_id,
            family_type=family_type,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context
        ) | {
            'admin_event_tab': 'admin-event-families-tab',
            'admin_families_show_details': SessionHandler.get_session_admin_families_show_details(
                web_context.request,
            ),
        }

        match modal:
            case None:
                pass
            case 'family':
                if data is None:
                    uniq_id: str | None = None
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
                    ranking_crosstable: bool = False
                    ranking_round: int | None = None
                    ranking_min_points: float | None = None
                    ranking_max_points: float | None = None
                    tournament_id: int | None = None
                    first: int | None = None
                    last: int | None = None
                    parts: int | None = None
                    number: int | None = None
                    message_default: bool = True
                    message_text: str | None = None
                    match action:
                        case 'update':
                            assert web_context.admin_family is not None
                            uniq_id = web_context.admin_family.stored_family.uniq_id
                            name = web_context.admin_family.stored_family.name
                        case 'create':
                            assert family_type is not None
                            uniq_id = web_context.admin_event.get_unused_family_uniq_id(
                                family_type=ScreenType(family_type)
                            )
                            name = web_context.admin_event.get_unused_family_name(
                                family_type=ScreenType(family_type)
                            )
                        case 'clone':
                            assert web_context.admin_family is not None
                            uniq_id = web_context.admin_event.get_unused_family_uniq_id(
                                base_uniq_id=web_context.admin_family.stored_family.uniq_id
                            )
                            name = web_context.admin_event.get_unused_family_name(
                                family_type=ScreenType(web_context.admin_family.type),
                                base_name=web_context.admin_family.stored_family.name,
                            )
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    match action:
                        case 'update' | 'clone':
                            if web_context.admin_family is None:
                                raise RuntimeError(
                                    f'{web_context.admin_family=} for [{action=}]'
                                )
                            public = web_context.admin_family.stored_family.public
                            tournament_id = (
                                web_context.admin_family.stored_family.tournament_id
                            )
                            columns = web_context.admin_family.stored_family.columns
                            font_size = web_context.admin_family.stored_family.font_size
                            menu_link = web_context.admin_family.stored_family.menu_link
                            menu_text = web_context.admin_family.stored_family.menu_text
                            menu = web_context.admin_family.stored_family.menu
                            timer_id = web_context.admin_family.stored_family.timer_id
                            first = web_context.admin_family.stored_family.first
                            last = web_context.admin_family.stored_family.last
                            match web_context.admin_family.type:
                                case ScreenType.BOARDS:
                                    pass
                                case ScreenType.INPUT:
                                    input_exit_button = web_context.admin_family.stored_family.input_exit_button
                                case ScreenType.PLAYERS:
                                    players_show_opponent = web_context.admin_family.stored_family.players_show_opponent
                                    players_show_unpaired = web_context.admin_family.stored_family.players_show_unpaired
                                case ScreenType.RANKING:
                                    ranking_crosstable = web_context.admin_family.stored_family.ranking_crosstable
                                    ranking_round = web_context.admin_family.stored_family.ranking_round
                                    ranking_min_points = web_context.admin_family.stored_family.ranking_min_points
                                    ranking_max_points = web_context.admin_family.stored_family.ranking_max_points
                                case _:
                                    raise ValueError(
                                        f'type=[{web_context.admin_family.type}]'
                                    )
                            parts = web_context.admin_family.stored_family.parts
                            number = web_context.admin_family.stored_family.number
                            message_default = (
                                web_context.admin_family.stored_family.message_default
                            )
                            message_text = (
                                web_context.admin_family.stored_family.message_text
                            )
                        case 'create':
                            public = True
                            message_default = True
                            tournament_id = list(
                                web_context.admin_event.tournaments_by_id.keys()
                            )[0]
                            match family_type:
                                case ScreenType.BOARDS:
                                    menu = '@boards'
                                case ScreenType.INPUT:
                                    menu = '@input'
                                case ScreenType.PLAYERS:
                                    menu = '@players'
                                case ScreenType.RANKING:
                                    menu = '@ranking'
                                case _:
                                    raise ValueError(f'family_type={family_type}')
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    data = {
                        'uniq_id': WebContext.value_to_form_data(uniq_id),
                        'public': WebContext.value_to_form_data(public),
                        'name': WebContext.value_to_form_data(name),
                        'tournament_id': WebContext.value_to_form_data(tournament_id),
                        'columns': WebContext.value_to_form_data(columns),
                        'font_size': WebContext.value_to_form_data(font_size),
                        'menu_link': WebContext.value_to_form_data(menu_link),
                        'menu_text': WebContext.value_to_form_data(menu_text),
                        'menu': WebContext.value_to_form_data(menu),
                        'timer_id': WebContext.value_to_form_data(timer_id),
                        'first': WebContext.value_to_form_data(first),
                        'last': WebContext.value_to_form_data(last),
                        'parts': WebContext.value_to_form_data(parts),
                        'number': WebContext.value_to_form_data(number),
                        'message_text_checkbox': WebContext.value_to_form_data(
                            message_default
                        ),
                        'message_text': WebContext.value_to_form_data(message_text),
                        'input_exit_button': WebContext.value_to_form_data(
                            input_exit_button
                        ),
                        'players_show_unpaired': WebContext.value_to_form_data(
                            players_show_unpaired
                        ),
                        'players_show_opponent': WebContext.value_to_form_data(
                            players_show_opponent
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
                    }
                    stored_family: StoredFamily = (
                        cls._admin_validate_family_update_data(
                            action, web_context, data
                        )
                    )
                    errors = stored_family.errors
                if errors is None:
                    errors = {}

                template_context |= {
                    'tournament_options': web_context.get_tournament_options(),
                    'screen_type_options': cls._get_screen_type_options(
                        family_screens_only=True
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
            case _:
                raise ValueError(f'modal=[{modal}]')
        return cls._admin_event_render(template_context)

    @get(
        path='/admin/event/{event_uniq_id:str}/families',
        name='admin-event-families-tab',
        cache=1,
    )
    async def htmx_admin_event_families_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        admin_families_show_details: bool | None,
    ) -> Template | ClientRedirect:
        if admin_families_show_details is not None:
            SessionHandler.set_session_admin_families_show_details(
                request, admin_families_show_details
            )
        return self._admin_event_families_render(
            request,
            event_uniq_id=event_uniq_id,
        )

    @get(
        path='/admin/family-modal/create/{event_uniq_id:str}/{family_type:str}',
        name='admin-family-create-modal',
        cache=1,
    )
    async def htmx_admin_family_create_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        family_type: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_families_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='family',
            action='create',
            family_id=None,
            family_type=family_type,
        )

    @get(
        path='/admin/family-modal/{action:str}/{event_uniq_id:str}/{family_id:int}',
        name='admin-family-modal',
        cache=1,
    )
    async def htmx_admin_family_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        action: str,
        family_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_families_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='family',
            action=action,
            family_id=family_id,
        )

    def _admin_family_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        action: str,
        family_id: int | None,
        family_type: str | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        match action:
            case 'update' | 'delete' | 'clone' | 'create':
                web_context: FamilyAdminWebContext = FamilyAdminWebContext(
                    request,
                    event_uniq_id=event_uniq_id,
                    family_id=family_id,
                    family_type=family_type,
                    data=data,
                )
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        stored_family: StoredFamily = self._admin_validate_family_update_data(
            action, web_context, data
        )
        if stored_family.errors:
            return self._admin_event_families_render(
                request,
                event_uniq_id=event_uniq_id,
                modal='family',
                action=action,
                family_id=family_id,
                family_type=family_type,
                data=data,
                errors=stored_family.errors,
            )
        event_loader: EventLoader = EventLoader.get(request=request)
        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
            match action:
                case 'create' | 'clone':
                    stored_family = event_database.add_stored_family(stored_family)
                    event_database.commit()
                    Message.success(
                        request,
                        _('Family [{family_uniq_id}] has been created.').format(
                            family_uniq_id=stored_family.uniq_id
                        ),
                    )
                case 'update':
                    stored_family = event_database.update_stored_family(stored_family)
                    event_database.commit()
                    Message.success(
                        request,
                        _('Family [{family_uniq_id}] has been updated.').format(
                            family_uniq_id=stored_family.uniq_id
                        ),
                    )
                case 'delete':
                    assert web_context.admin_family is not None
                    event_database.delete_stored_family(web_context.admin_family.id)
                    event_database.commit()
                    Message.success(
                        request,
                        _('Family [{family_uniq_id}] has been deleted.').format(
                            family_uniq_id=web_context.admin_family.uniq_id
                        ),
                    )
                case _:
                    raise ValueError(f'action=[{action}]')
        event_loader.clear_cache(event_uniq_id)
        return self._admin_event_families_render(request, event_uniq_id=event_uniq_id)

    @post(
        path='/admin/family-create/{event_uniq_id:str}/{family_type:str}',
        name='admin-family-create',
    )
    async def htmx_admin_family_create(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        family_type: str,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_family_update(
            request,
            event_uniq_id=event_uniq_id,
            action='create',
            family_id=None,
            family_type=family_type,
            data=data,
        )

    @post(
        path='/admin/family-clone/{event_uniq_id:str}/{family_id:int}',
        name='admin-family-clone',
    )
    async def htmx_admin_family_clone(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        family_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_family_update(
            request,
            event_uniq_id=event_uniq_id,
            action='clone',
            family_id=family_id,
            family_type=None,
            data=data,
        )

    @patch(
        path='/admin/family-update/{event_uniq_id:str}/{family_id:int}',
        name='admin-family-update',
    )
    async def htmx_admin_family_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        family_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_family_update(
            request,
            event_uniq_id=event_uniq_id,
            action='update',
            family_id=family_id,
            family_type=None,
            data=data,
        )

    @delete(
        path='/admin/family-delete/{event_uniq_id:str}/{family_id:int}',
        name='admin-family-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_family_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        family_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_family_update(
            request,
            event_uniq_id=event_uniq_id,
            action='delete',
            family_id=family_id,
            family_type=None,
            data=data,
        )
