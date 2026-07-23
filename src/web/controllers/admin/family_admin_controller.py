from typing import Annotated, Any

from litestar import post, get, patch, delete
from litestar.exceptions import ClientException, NotFoundException
from litestar.plugins.htmx import HTMXRequest
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK
from litestar_htmx import HTMXTemplate

from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.access_levels.actions import AuthAction
from data.screens.family import Family
from utils import Utils
from data.screens.manager import ScreenTypeManager
from data.screens.screen_types import ScreenType
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredFamily
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.guards import EventGuard, ActionGuard
from web.messages import Message
from web.session import SessionFamiliesShowDetails


class FamilyAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        family_id: int | None = None,
        family_type_id: str | None = None,
        reload_event: bool = False,
    ):
        super().__init__(request, reload_event)
        if self.admin_event is None:
            raise RuntimeError('admin_event not defined')
        self.admin_family: Family | None = None
        if family_id:
            try:
                self.admin_family = self.admin_event.families_by_id[family_id]
            except KeyError:
                raise NotFoundException(f'Family [{family_id}] not found.')

        self.family_type_id: str | None = None
        if self.admin_family:
            self.family_type_id = self.admin_family.type
        elif family_type_id:
            if family_type_id not in ScreenTypeManager(self.get_admin_event()).ids():
                raise NotFoundException(f'Unknown screen type [{family_type_id}].')
            self.family_type_id = family_type_id

    def get_admin_family(self) -> Family:
        assert self.admin_family is not None
        return self.admin_family

    @property
    def family_type(self) -> 'ScreenType | None':
        if self.family_type_id is None:
            return None
        return ScreenTypeManager(self.get_admin_event()).get_object(self.family_type_id)

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_family': self.admin_family,
            'family_type': self.family_type,
            'family_screen_types': [
                type_
                for type_ in ScreenTypeManager(self.get_admin_event()).objects()
                if type_.families_allowed
                and type_.supports_event_type(self.get_admin_event().event_type)
            ],
        }


class FamilyAdminController(BaseEventAdminController):
    guards = [
        EventGuard(),
        ActionGuard(AuthAction.MANAGE_SCREENS),
    ]

    @staticmethod
    def _admin_validate_family_update_data(
        action: str,
        web_context: FamilyAdminWebContext,
        data: dict[str, str] | None = None,
    ) -> StoredFamily:
        errors: dict[str, str] = {}
        event = web_context.get_admin_event()
        if data is None:
            data = {}
        field: str
        type_: str
        match action:
            case 'create':
                family_type = web_context.family_type
                assert family_type is not None
                assert web_context.family_type_id is not None
                type_ = web_context.family_type_id
                if not family_type.supports_event_type(event.event_type):
                    raise ValueError(
                        f'Screen type [{type_}] is not available for '
                        f'[{event.event_type}] events.'
                    )
            case 'update' | 'clone' | 'delete':
                type_ = web_context.get_admin_family().stored_family.type
            case _:
                raise ValueError(f'action=[{action}]')
        menu_text: str | None = None
        columns: int | None = None
        font_size: int | None = None
        timer_id: int | None = None
        tournament_id: int | None = None
        first: int | None = None
        last: int | None = None
        parts: int | None = None
        number: int | None = None
        message_default: bool = True
        message_text: str | None = None
        # Type-specific StoredFamily fields, extracted by the screen type.
        type_values: dict[str, Any] = {}
        name = WebContext.form_data_to_str(data, 'name')
        public = WebContext.form_data_to_bool(data, 'public')
        match action:
            case 'create' | 'clone' | 'update':
                field = 'tournament_id'
                try:
                    if len(event.tournaments_by_id) == 1:
                        tournament_id = list(event.tournaments_by_id.keys())[0]
                        data[field] = WebContext.value_to_form_data(tournament_id)
                    else:
                        tournament_id = WebContext.form_data_to_int(data, field)
                        if not tournament_id:
                            errors[field] = _('Please choose the tournament.')
                        elif tournament_id not in event.tournaments_by_id:
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
                family_type = web_context.family_type
                assert family_type is not None
                type_values = family_type.read_form_data(data, errors, event)
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
                if action == 'update':
                    uniq_id = web_context.get_admin_family().uniq_id
                else:
                    uniq_id = event.get_unused_family_uniq_id(
                        web_context.family_type,
                        Utils.name_to_uniq_id(name) if name else None,
                    )
            case 'delete':
                uniq_id = ''
                stored_family = web_context.get_admin_family().stored_family
                tournament_id = stored_family.tournament_id
                name = stored_family.name
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
            menu_text=menu_text or '',
            timer_id=timer_id,
            first=first,
            last=last,
            parts=parts,
            number=number,
            message_default=message_default,
            message_text=message_text,
            errors=errors,
            **type_values,
        )

    @classmethod
    def _admin_event_families_render(
        cls,
        request: HTMXRequest,
        reload_event: bool = False,
        modal: str | None = None,
        action: str | None = None,
        family_id: int | None = None,
        family_type: str | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template:
        web_context = FamilyAdminWebContext(
            request,
            family_id=family_id,
            family_type_id=family_type,
            reload_event=reload_event,
        )
        event = web_context.get_admin_event()
        template_context = web_context.template_context | {
            'admin_event_tab': 'admin-event-families-tab',
            'show_details': SessionFamiliesShowDetails(request).get(),
        }

        match modal:
            case None:
                pass
            case 'family':
                if data is None:
                    name: str | None = None
                    public: bool | None = None
                    menu_text: str | None = None
                    columns: int | None = None
                    font_size: int | None = None
                    timer_id: int | None = None
                    tournament_id: int | None = None
                    first: int | None = None
                    last: int | None = None
                    parts: int | None = None
                    number: int | None = None
                    message_default: bool = True
                    message_text: str | None = None
                    # Type-specific form values, provided by the screen type.
                    type_values: dict[str, Any] = {}
                    match action:
                        case 'update':
                            name = web_context.get_admin_family().stored_family.name
                        case 'create':
                            # No default name: an unnamed multi-screen is named
                            # automatically (as for single screens).
                            pass
                        case 'clone':
                            family = web_context.get_admin_family()
                            name = event.get_unused_family_name(
                                family_type=family.screen_type,
                                base_name=family.stored_family.name,
                            )
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    match action:
                        case 'update' | 'clone':
                            family = web_context.get_admin_family()
                            stored_family = family.stored_family
                            public = stored_family.public
                            tournament_id = stored_family.tournament_id
                            columns = stored_family.columns
                            font_size = stored_family.font_size
                            menu_text = stored_family.menu_text
                            timer_id = stored_family.timer_id
                            first = stored_family.first
                            last = stored_family.last
                            type_values = family.screen_type.default_family_form_data(
                                family
                            )
                            parts = stored_family.parts
                            number = stored_family.number
                            message_default = stored_family.message_default
                            message_text = stored_family.message_text
                        case 'create':
                            public = True
                            message_default = True
                            tournament_id = list(event.tournaments_by_id.keys())[0]
                            create_type = web_context.family_type
                            assert create_type is not None
                            type_values = create_type.create_form_data(event)
                            columns = type_values.pop('columns', None)
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    form_values: dict[str, Any] = {
                        'public': public,
                        'name': name,
                        'tournament_id': tournament_id,
                        'columns': columns,
                        'font_size': font_size,
                        'menu_text': menu_text,
                        'timer_id': timer_id,
                        'first': first,
                        'last': last,
                        'parts': parts,
                        'number': number,
                        'message_text_checkbox': message_default,
                        'message_text': message_text,
                    }
                    form_values.update(type_values)
                    data = WebContext.values_dict_to_form_data(form_values)
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
                        family_screens_only=True, event=event
                    ),
                    'timer_options': cls._get_timer_options(event),
                    'ranking_crosstable_options': cls._get_ranking_crosstable_options(),
                    'family_uniq_ids': list(event.families_by_uniq_id.keys()),
                    'players_player_format_options': web_context.get_players_screen_player_format_options(),
                    'players_board_format_options': web_context.get_players_screen_board_format_options(),
                    'players_opponent_format_options': web_context.get_players_screen_opponent_format_options(),
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case _:
                raise ValueError(f'modal=[{modal}]')
        return cls._admin_base_event_render(template_context)

    @get(
        path='/event/{event_uniq_id:str}/families',
        name='admin-event-families-tab',
    )
    async def htmx_admin_event_families_tab(
        self,
        request: HTMXRequest,
        show_details: bool | None,
    ) -> Template:
        if show_details is not None:
            SessionFamiliesShowDetails(request).set(show_details)
        return self._admin_event_families_render(request)

    @staticmethod
    def _family_modal_live_data(request: HTMXRequest) -> dict[str, str] | None:
        """When the modal reloads itself (e.g. on tournament change, to
        refresh the tournament-dependent labels) the current form values
        come along as query parameters — keep them instead of rebuilding
        the defaults. The ``live`` marker distinguishes a reload from a
        plain modal open."""
        if request.query_params.get('live'):
            return {
                key: value[0] if isinstance(value, list) else value
                for key, value in request.query_params.dict().items()
                if key != 'live'
            }
        return None

    @get(
        path='/family-modal/create/{event_uniq_id:str}/{family_type:str}',
        name='admin-family-create-modal',
    )
    async def htmx_admin_family_create_modal(
        self,
        request: HTMXRequest,
        family_type: str,
    ) -> Template:
        return self._admin_event_families_render(
            request,
            modal='family',
            action='create',
            family_id=None,
            family_type=family_type,
            data=self._family_modal_live_data(request),
        )

    @get(
        path='/family-modal/{action:str}/{event_uniq_id:str}/{family_id:int}',
        name='admin-family-modal',
    )
    async def htmx_admin_family_modal(
        self,
        request: HTMXRequest,
        action: str,
        family_id: int | None,
    ) -> Template:
        return self._admin_event_families_render(
            request,
            modal='family',
            action=action,
            family_id=family_id,
            data=self._family_modal_live_data(request),
        )

    def _admin_family_update(
        self,
        request: HTMXRequest,
        action: str,
        family_id: int | None,
        family_type: str | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = FamilyAdminWebContext(
            request,
            family_id=family_id,
            family_type_id=family_type,
        )
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        stored_family: StoredFamily = self._admin_validate_family_update_data(
            action, web_context, data
        )
        if stored_family.errors:
            return self._admin_event_families_render(
                request,
                modal='family',
                action=action,
                family_id=family_id,
                family_type=family_type,
                data=data,
                errors=stored_family.errors,
            )
        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
            match action:
                case 'create' | 'clone':
                    stored_family = event_database.add_stored_family(stored_family)
                    Message.success(
                        request,
                        _('Multi-Screen [{family_uniq_id}] has been created.').format(
                            family_uniq_id=stored_family.uniq_id
                        ),
                    )
                case 'update':
                    stored_family = event_database.update_stored_family(stored_family)
                    Message.success(
                        request,
                        _('Multi-Screen [{family_uniq_id}] has been updated.').format(
                            family_uniq_id=stored_family.uniq_id
                        ),
                    )
                case 'delete':
                    assert web_context.admin_family is not None
                    event_database.delete_stored_family(web_context.admin_family.id)
                    Message.success(
                        request,
                        _('Multi-Screen [{family_uniq_id}] has been deleted.').format(
                            family_uniq_id=web_context.admin_family.uniq_id
                        ),
                    )
                case _:
                    raise ValueError(f'action=[{action}]')

        return self._admin_event_families_render(request, reload_event=True)

    @post(
        path='/family-create/{event_uniq_id:str}/{family_type:str}',
        name='admin-family-create',
        guards=[ActionGuard(AuthAction.MANAGE_SCREENS)],
    )
    async def htmx_admin_family_create(
        self,
        request: HTMXRequest,
        family_type: str,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        return self._admin_family_update(
            request,
            action='create',
            family_id=None,
            family_type=family_type,
            data=data,
        )

    @post(
        path='/family-clone/{event_uniq_id:str}/{family_id:int}',
        name='admin-family-clone',
    )
    async def htmx_admin_family_clone(
        self,
        request: HTMXRequest,
        family_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        return self._admin_family_update(
            request,
            action='clone',
            family_id=family_id,
            family_type=None,
            data=data,
        )

    @patch(
        path='/family-update/{event_uniq_id:str}/{family_id:int}',
        name='admin-family-update',
    )
    async def htmx_admin_family_update(
        self,
        request: HTMXRequest,
        family_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        return self._admin_family_update(
            request,
            action='update',
            family_id=family_id,
            family_type=None,
            data=data,
        )

    @patch(
        path='/family-uniq-id-update/{event_uniq_id:str}/{family_id:int}',
        name='admin-family-uniq-id-update',
    )
    async def htmx_admin_family_uniq_id_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        family_id: int,
    ) -> HTMXTemplate:
        web_context = FamilyAdminWebContext(request, family_id)
        event = web_context.get_admin_event()
        family = web_context.get_admin_family()
        new_uniq_id = WebContext.form_data_to_str(data, 'uniq_id')
        if (
            not new_uniq_id
            or not SharlyChessConfig.uniq_id_regex.match(new_uniq_id)
            or (
                new_uniq_id != family.uniq_id
                and new_uniq_id in event.families_by_uniq_id.keys()
            )
        ):
            # No precise error (validated in JS)
            raise ClientException(f'Invalid uniq ID [{new_uniq_id}].')
        stored_family = family.stored_family
        assert stored_family is not None
        stored_family.uniq_id = new_uniq_id
        with EventDatabase(event.uniq_id, True) as database:
            database.update_stored_family(stored_family)

        web_context = FamilyAdminWebContext(request, family_id, reload_event=True)
        event = web_context.get_admin_event()
        return HTMXTemplate(
            template_name='/admin/families/family_update_modal_header.html',
            context=web_context.template_context
            | {'family_uniq_ids': list(event.families_by_uniq_id.keys())},
            re_swap='innerHTML',
            re_target='.modal-header',
        )

    @delete(
        path='/family-delete/{event_uniq_id:str}/{family_id:int}',
        name='admin-family-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_family_delete(
        self,
        request: HTMXRequest,
        family_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        return self._admin_family_update(
            request,
            action='delete',
            family_id=family_id,
            family_type=None,
            data=data,
        )
