from logging import Logger
from typing import Annotated, Any

import requests
import validators
from litestar import post, get, delete, patch
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common.logger import get_logger
from data.loader import EventLoader
from data.screen import Screen
from data.screen_set import ScreenSet
from data.util import ScreenType
from database.sqlite import EventDatabase
from database.store import StoredScreen, StoredScreenSet
from web.controllers.admin.event_admin_controller import EventAdminWebContext, AbstractEventAdminController
from web.controllers.index_controller import WebContext, AbstractController
from web.messages import Message

logger: Logger = get_logger()


class ScreenAdminWebContext(EventAdminWebContext):
    def __init__(
            self, request: HTMXRequest,
            event_uniq_id: str,
            admin_event_tab: str | None,
            screen_id: int | None,
            screen_set_id: int | None,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ] | None,
    ):
        super().__init__(request, event_uniq_id=event_uniq_id, admin_event_tab=admin_event_tab, data=data)
        self.admin_screen: Screen | None = None
        self.admin_screen_set: ScreenSet | None = None
        if self.error:
            return
        if screen_id:
            try:
                self.admin_screen = self.admin_event.basic_screens_by_id[screen_id]
            except KeyError:
                self._redirect_error(f'L\'écran [{screen_id}] n\'existe pas')
                return
        if screen_set_id:
            try:
                self.admin_screen_set = self.admin_screen.screen_sets_by_id[screen_set_id]
            except KeyError:
                self._redirect_error(
                    f'L\'ensemble d\'écran [{screen_set_id}] n\'existe pas pour l\'écran '
                    f'[{self.admin_screen.uniq_id}]')
                return

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_screen': self.admin_screen,
            'admin_screen_set': self.admin_screen_set,
        }


class ScreenAdminController(AbstractEventAdminController):

    @staticmethod
    def _admin_validate_screen_update_data(
            action: str,
            web_context: ScreenAdminWebContext,
            data: dict[str, str] | None = None,
    ) -> StoredScreen:
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        type: str
        field: str = 'type'
        match action:
            case 'create':
                type = WebContext.form_data_to_str(data, field)
                match type:
                    case 'boards' | 'input' | 'players' | 'results' | 'image':
                        pass
                    case None:
                        errors[field] = 'Veuillez choisir le type d\'écran.'
                    case _:
                        raise ValueError(f'type=[{type}]')
            case 'update' | 'clone' | 'delete':
                type = web_context.admin_screen.stored_screen.type
            case _:
                raise ValueError(f'action=[{action}]')
        field = 'uniq_id'
        uniq_id: str = WebContext.form_data_to_str(data, field)
        name: str | None = None
        public: bool | None = None
        if action == 'delete':
            pass
        else:
            if not uniq_id:
                errors[field] = 'Veuillez entrer l\'identifiant de l\'écran.'
            elif ':' in uniq_id:
                errors[field] = 'Le caractère [:] est interdit.'
            else:
                match action:
                    case 'create' | 'clone':
                        if uniq_id in web_context.admin_event.screens_by_uniq_id:
                            errors[field] = f'L\'écran [{uniq_id}] existe déjà.'
                    case 'update':
                        if uniq_id != web_context.admin_screen.uniq_id \
                                and uniq_id in web_context.admin_event.screens_by_uniq_id:
                            errors[field] = f'L\'écran [{uniq_id}] existe déjà.'
                    case _:
                        raise ValueError(f'action=[{action}]')
            name = WebContext.form_data_to_str(data, 'name')
            public = WebContext.form_data_to_bool(data, 'public')
        menu_link: bool | None = None
        menu_text: str | None = None
        menu: str | None = None
        columns: int | None = None
        timer_id: int | None = None
        input_exit_button: bool | None = None
        players_show_unpaired: bool | None = None
        results_limit: int | None = None
        results_max_age: int | None = None
        results_tournament_ids: list[int] | None = None
        background_image: str | None = None
        background_color: str | None = None
        match action:
            case 'create':
                if type != ScreenType.Image:
                    menu_link = True
                    menu_text = ''
                    menu = ''
                pass
            case 'delete' | 'clone':
                pass
            case 'update':
                field = 'columns'
                try:
                    columns = WebContext.form_data_to_int(data, field, minimum=1)
                except ValueError:
                    errors[field] = 'Un entier positif est attendu.'
                if type != ScreenType.Image:
                    menu_link = WebContext.form_data_to_bool(data, 'menu_link', False)
                    menu_text = WebContext.form_data_to_str(data, 'menu_text', '')
                    menu = WebContext.form_data_to_str(data, 'menu', '')
                field = 'timer_id'
                try:
                    timer_id = WebContext.form_data_to_int(data, field)
                    if timer_id and timer_id not in web_context.admin_event.timers_by_id:
                        errors[field] = f'Le chronomètre [{timer_id}] n\'existe pas.'
                except ValueError:
                    errors[field] = 'Un entier positif est attendu.'
                match web_context.admin_screen.type:
                    case ScreenType.Boards:
                        pass
                    case ScreenType.Input:
                        input_exit_button = WebContext.form_data_to_bool(data, 'input_exit_button')
                    case ScreenType.Players:
                        players_show_unpaired = WebContext.form_data_to_bool(data, 'players_show_unpaired')
                    case ScreenType.Results:
                        field = 'results_limit'
                        try:
                            results_limit = WebContext.form_data_to_int(data, field)
                        except ValueError:
                            errors[field] = 'Un entier positif est attendu.'
                        field = 'results_max_age'
                        try:
                            results_max_age = WebContext.form_data_to_int(data, field)
                        except ValueError:
                            errors[field] = 'Un entier positif est attendu.'
                        results_tournament_ids = []
                        for tournament_id in web_context.admin_event.tournaments_by_id:
                            field = f'results_tournament_{tournament_id}'
                            if WebContext.form_data_to_bool(data, field):
                                results_tournament_ids.append(tournament_id)
                    case ScreenType.Image:
                        field = 'background_image'
                        background_image = WebContext.form_data_to_str(data, field, '')
                        if not background_image:
                            errors[field] = f'Veuillez préciser l\'URL de l\'image.'
                        elif not validators.url(background_image):
                            errors[field] = f'L\'URL [{background_image}] n\'est pas valide.'
                        else:
                            try:
                                response = requests.get(background_image)
                                if response.status_code != 200:
                                    errors[field] = \
                                        f'L\'URL [{background_image}] est en erreur (code [{response.status_code}]).'
                            except requests.ConnectionError as ce:
                                errors[field] = f'L\'URL [{background_image}] est en erreur ([{ce}]).'
                        field: str = 'background_color'
                        color_checkbox = WebContext.form_data_to_bool(data, field + '_checkbox')
                        if not color_checkbox:
                            try:
                                background_color = WebContext.form_data_to_rgb(data, field)
                            except ValueError:
                                errors[field] = f'La couleur [{data[field]}] n\'est pas valide (attendu [#RRGGBB]).'
                    case _:
                        raise ValueError(f'type=[{web_context.admin_screen.type}]')
            case _:
                raise ValueError(f'action=[{action}]')
        return StoredScreen(
            id=web_context.admin_screen.id if action != 'create' else None,
            uniq_id=uniq_id,
            type=type,
            public=public,
            name=name,
            columns=columns,
            menu_link=menu_link,
            menu_text=menu_text,
            menu=menu,
            timer_id=timer_id,
            input_exit_button=input_exit_button,
            players_show_unpaired=players_show_unpaired,
            results_limit=results_limit,
            results_max_age=results_max_age,
            results_tournament_ids=results_tournament_ids,
            background_image=background_image,
            background_color=background_color,
            errors=errors,
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
        field: str = 'name'
        name = WebContext.form_data_to_str(data, field)
        field: str = 'tournament_id'
        try:
            if len(web_context.admin_screen.event.tournaments_by_id) == 1:
                tournament_id = list(web_context.admin_screen.event.tournaments_by_id.keys())[0]
                data[field] = WebContext.value_to_form_data(tournament_id)
            else:
                tournament_id = WebContext.form_data_to_int(data, field)
                if not tournament_id:
                    errors[field] = f'Veuillez indiquer le tournoi.'
                elif tournament_id not in web_context.admin_screen.event.tournaments_by_id:
                    errors[field] = f'Le tournoi [{tournament_id}] n\'existe pas.'
        except ValueError:
            errors[field] = 'Un entier positif est attendu.'
        field: str = 'first'
        try:
            first = WebContext.form_data_to_int(data, field, minimum=1)
        except ValueError:
            errors[field] = 'Un entier positif est attendu.'
        field: str = 'last'
        try:
            last = WebContext.form_data_to_int(data, field, minimum=1)
        except ValueError:
            errors[field] = 'Un entier positif est attendu.'
        if first and last and first > last:
            error: str = f'Les nombres {first} et {last} ne sont pas compatibles ({first} > {last}).'
            errors['first'] = error
            errors['last'] = error
        fixed_boards_str: str | None = None
        if web_context.admin_screen.type in [ScreenType.Boards, ScreenType.Input]:
            fixed_boards_str = WebContext.form_data_to_str(data, 'fixed_boards_str')
            if fixed_boards_str:
                for fixed_board_str in list(map(str.strip, fixed_boards_str.split(','))):
                    if fixed_board_str:
                        try:
                            int(fixed_board_str)
                        except ValueError:
                            errors['fixed_boards_str'] = f'Le numéro d\'échiquier {fixed_board_str} n\'est pas valide.'
                            break
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
            screen_set_id: int | None = None,
            data: dict[str, str] | None = None,
            errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: ScreenAdminWebContext = ScreenAdminWebContext(
            request, event_uniq_id=event_uniq_id, admin_event_tab='screens', screen_id=screen_id,
            screen_set_id=screen_set_id, data=data)
        if web_context.error:
            return web_context.error
        template_context: dict[str, Any] = cls._get_admin_event_render_context(web_context)
        match modal:
            case None:
                pass
            case 'screen':
                if data is None:
                    data: dict[str, str] = {}
                    match action:
                        case 'update':
                            data['uniq_id'] = WebContext.value_to_form_data(
                                web_context.admin_screen.stored_screen.uniq_id)
                        case 'create' | 'clone':
                            data['uniq_id'] = ''
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    match action:
                        case 'update' | 'clone':
                            data['public'] = WebContext.value_to_form_data(
                                web_context.admin_screen.stored_screen.public)
                            data['name'] = WebContext.value_to_form_data(web_context.admin_screen.stored_screen.name)
                            data['columns'] = WebContext.value_to_form_data(
                                web_context.admin_screen.stored_screen.columns)
                            if web_context.admin_screen.type != ScreenType.Image:
                                data['menu_link'] = WebContext.value_to_form_data(
                                    web_context.admin_screen.stored_screen.menu_link)
                                data['menu_text'] = WebContext.value_to_form_data(
                                    web_context.admin_screen.stored_screen.menu_text)
                                data['menu'] = WebContext.value_to_form_data(
                                    web_context.admin_screen.stored_screen.menu)
                            data['timer_id'] = WebContext.value_to_form_data(
                                web_context.admin_screen.stored_screen.timer_id)
                            match web_context.admin_screen.type:
                                case ScreenType.Boards:
                                    pass
                                case ScreenType.Input:
                                    data['input_exit_button'] = WebContext.value_to_form_data(
                                        web_context.admin_screen.stored_screen.input_exit_button)
                                case ScreenType.Players:
                                    data['players_show_unpaired'] = WebContext.value_to_form_data(
                                        web_context.admin_screen.stored_screen.players_show_unpaired)
                                case ScreenType.Results:
                                    data['results_limit'] = WebContext.value_to_form_data(
                                        web_context.admin_screen.stored_screen.results_limit)
                                    data['results_max_age'] = WebContext.value_to_form_data(
                                        web_context.admin_screen.stored_screen.results_max_age)
                                    for tournament_id in web_context.admin_event.tournaments_by_id:
                                        data[f'results_tournament_{tournament_id}'] = WebContext.value_to_form_data(
                                            tournament_id
                                            in web_context.admin_screen.stored_screen.results_tournament_ids)
                                case ScreenType.Image:
                                    data['background_image'] = WebContext.value_to_form_data(
                                        web_context.admin_screen.stored_screen.background_image)
                                    data['background_color'] = WebContext.value_to_form_data(
                                        web_context.admin_screen.background_color)
                                    data['background_color_checkbox'] = WebContext.value_to_form_data(
                                        web_context.admin_screen.stored_screen.background_color is None)
                                case _:
                                    raise ValueError(f'action={action}')
                        case 'create':
                            data['type'] = ''
                            data['public'] = WebContext.value_to_form_data(True)
                            data['uniq_id'] = ''
                            data['name'] = ''
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    stored_screen: StoredScreen = cls._admin_validate_screen_update_data(action, web_context, data)
                    errors = stored_screen.errors
                if errors is None:
                    errors = {}
                template_context |= {
                    'screen_type_options': cls._get_screen_type_options(family_screens_only=False),
                    'timer_options': cls._get_timer_options(web_context.admin_event),
                    'input_exit_button_options': cls._get_input_exit_button_options(),
                    'players_show_unpaired_options': cls._get_players_show_unpaired_options(),
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case 'screen_sets':
                if data is None:
                    if web_context.admin_screen_set:
                        data = {
                            'tournament_id': WebContext.value_to_form_data(
                                web_context.admin_screen_set.stored_screen_set.tournament_id),
                            'fixed_boards_str': WebContext.value_to_form_data(
                                web_context.admin_screen_set.stored_screen_set.fixed_boards_str),
                            'name': WebContext.value_to_form_data(web_context.admin_screen_set.stored_screen_set.name),
                            'first': WebContext.value_to_form_data(
                                web_context.admin_screen_set.stored_screen_set.first),
                            'last': WebContext.value_to_form_data(web_context.admin_screen_set.stored_screen_set.last),
                        }
                        if web_context.admin_screen.type in [ScreenType.Boards, ScreenType.Input]:
                            data['fixed_boards_str'] = WebContext.value_to_form_data(
                                web_context.admin_screen_set.stored_screen_set.fixed_boards_str)
                        stored_screen_set = cls._admin_validate_screen_set_update_data(web_context, data)
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
        path='/admin/screen-modal/create/{event_uniq_id:str}',
        name='admin-screen-create-modal',
        cache=1,
    )
    async def htmx_admin_screen_create_modal(
            self, request: HTMXRequest,
            event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_screens_render(
            request, event_uniq_id=event_uniq_id, modal='screen', action='create', screen_id=None)

    @get(
        path='/admin/screen-modal/{action:str}/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-modal',
        cache=1,
    )
    async def htmx_admin_screen_modal(
            self, request: HTMXRequest,
            action: str,
            event_uniq_id: str,
            screen_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_screens_render(
            request, event_uniq_id=event_uniq_id, modal='screen', action=action, screen_id=screen_id)

    def _admin_screen_update(
            self, request: HTMXRequest,
            event_uniq_id: str,
            action: str,
            screen_id: int | None,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
    ) -> Template | ClientRedirect:
        match action:
            case 'update' | 'delete' | 'clone' | 'create':
                web_context: ScreenAdminWebContext = ScreenAdminWebContext(
                    request, event_uniq_id=event_uniq_id, admin_event_tab='screens', screen_id=screen_id,
                    screen_set_id=None, data=data)
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        stored_screen: StoredScreen | None = self._admin_validate_screen_update_data(action, web_context, data)
        if stored_screen.errors:
            return self._admin_event_screens_render(
                request, event_uniq_id=event_uniq_id, modal='screen', action=action, screen_id=screen_id,
                data=data, errors=stored_screen.errors)
        event_loader: EventLoader = EventLoader.get(request=request)
        with EventDatabase(web_context.admin_event.uniq_id, write=True) as event_database:
            match action:
                case 'create':
                    stored_screen = event_database.add_stored_screen(stored_screen)
                    if stored_screen.type in [ScreenType.Boards, ScreenType.Input, ScreenType.Players]:
                        event_database.add_stored_screen_set(
                            stored_screen.id, web_context.admin_event.tournaments_sorted_by_uniq_id[0].id)
                    event_database.commit()
                    Message.success(request, f'L\'écran [{stored_screen.uniq_id}] a été créé.')
                    event_loader.clear_cache(event_uniq_id)
                    return self._admin_event_screens_render(
                        request, event_uniq_id=event_uniq_id, modal='screen', action='update',
                        screen_id=stored_screen.id)
                case 'update':
                    stored_screen = event_database.update_stored_screen(stored_screen)
                    event_database.commit()
                    Message.success(request, f'L\'écran [{stored_screen.uniq_id}] a été modifié.')
                    event_loader.clear_cache(event_uniq_id)
                    return self._admin_event_screens_render(request, event_uniq_id=event_uniq_id)
                case 'delete':
                    event_database.delete_stored_screen(web_context.admin_screen.id)
                    event_database.commit()
                    Message.success(request, f'L\'écran [{web_context.admin_screen.uniq_id}] a été supprimé.')
                    event_loader.clear_cache(event_uniq_id)
                    return self._admin_event_screens_render(request, event_uniq_id=event_uniq_id)
                case 'clone':
                    stored_screen = event_database.clone_stored_screen(
                        web_context.admin_screen.id, stored_screen.uniq_id, WebContext.form_data_to_str(data, 'name'))
                    event_database.commit()
                    Message.success(
                        request,
                        f'L\'écran [{web_context.admin_screen.uniq_id}] a été dupliqué ([{stored_screen.uniq_id}]).')
                    event_loader.clear_cache(event_uniq_id)
                    return self._admin_event_screens_render(
                        request, event_uniq_id=event_uniq_id, modal='screen', action='update',
                        screen_id=stored_screen.id)
                case _:
                    raise ValueError(f'action=[{action}]')

    @post(
        path='/admin/screen-create/{event_uniq_id:str}',
        name='admin-screen-create'
    )
    async def htmx_admin_screen_create(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_screen_update(
            request, event_uniq_id=event_uniq_id, action='create', screen_id=None, data=data)

    @post(
        path='/admin/screen-clone/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-clone',
    )
    async def htmx_admin_screen_clone(
            self, request: HTMXRequest,
            event_uniq_id: str,
            screen_id: int,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
    ) -> Template | ClientRedirect:
        return self._admin_screen_update(
            request, event_uniq_id=event_uniq_id, action='clone', screen_id=screen_id, data=data)

    @patch(
        path='/admin/screen-update/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-update',
    )
    async def htmx_admin_screen_update(
            self, request: HTMXRequest,
            event_uniq_id: str,
            screen_id: int,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
    ) -> Template | ClientRedirect:
        return self._admin_screen_update(
            request, event_uniq_id=event_uniq_id, action='update', screen_id=screen_id, data=data)

    @delete(
        path='/admin/screen-delete/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_screen_delete(
            self, request: HTMXRequest,
            event_uniq_id: str,
            screen_id: int,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
    ) -> Template | ClientRedirect:
        return self._admin_screen_update(
            request, event_uniq_id=event_uniq_id, action='delete', screen_id=screen_id, data=data)

    @get(
        path='/admin/screen-sets-modal/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-sets-modal',
        cache=1,
    )
    async def htmx_admin_screen_sets_modal(
            self, request: HTMXRequest,
            event_uniq_id: str,
            screen_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_event_screens_render(
            request, event_uniq_id=event_uniq_id, modal='screen_sets', screen_id=screen_id, screen_set_id=None)

    @get(
        path='/admin/screen-sets-set-modal/{event_uniq_id:str}/{screen_id:int}/{screen_set_id:int}',
        name='admin-screen-sets-set-modal',
        cache=1,
    )
    async def htmx_admin_screen_sets_set_modal(
            self, request: HTMXRequest,
            event_uniq_id: str,
            screen_id: int,
            screen_set_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_event_screens_render(
            request, event_uniq_id=event_uniq_id, modal='screen_sets', screen_id=screen_id, screen_set_id=screen_set_id)

    def _admin_screen_sets_update(
            self, request: HTMXRequest,
            event_uniq_id: str,
            screen_id: int,
            screen_set_id: int | None,
            action: str,
            data: Annotated[dict[str, str | list[int]], Body(media_type=RequestEncodingType.URL_ENCODED), ],
    ) -> Template | ClientRedirect:
        match action:
            case 'delete' | 'clone' | 'update' | 'add' | 'reorder':
                web_context: ScreenAdminWebContext = ScreenAdminWebContext(
                    request, event_uniq_id=event_uniq_id, admin_event_tab='screens', screen_id=screen_id,
                    screen_set_id=screen_set_id, data=data)
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        event_loader: EventLoader = EventLoader.get(request=request)
        match action:
            case 'delete':
                if len(web_context.admin_screen.screen_sets_sorted_by_order) <= 1:
                    return AbstractController.redirect_error(
                        request, f'Le dernier ensemble d\'un écran ne peut être supprimé.')
            case 'update' | 'clone' | 'add' | 'reorder':
                pass
            case _:
                raise ValueError(f'action=[{action}]')
        next_screen_set_id: int | None = None
        with (EventDatabase(web_context.admin_event.uniq_id, write=True) as event_database):
            match action:
                case 'update':
                    stored_screen_set: StoredScreenSet = self._admin_validate_screen_set_update_data(web_context, data)
                    if stored_screen_set.errors:
                        return self._admin_event_screens_render(
                            request, event_uniq_id=event_uniq_id, modal='screen_sets', screen_id=screen_id,
                            screen_set_id=screen_set_id, data=data, errors=stored_screen_set.errors)
                    event_database.update_stored_screen_set(stored_screen_set)
                case 'delete':
                    event_database.delete_stored_screen_set(
                        web_context.admin_screen_set.id, web_context.admin_screen.id)
                case 'clone':
                    stored_screen_set = event_database.clone_stored_screen_set(
                        web_context.admin_screen_set.id, web_context.admin_screen.id)
                    next_screen_set_id = stored_screen_set.id
                case 'add':
                    stored_screen_set = event_database.add_stored_screen_set(
                        web_context.admin_screen.id, list(web_context.admin_event.tournaments_by_id.keys())[0])
                    next_screen_set_id = stored_screen_set.id
                case 'reorder':
                    event_database.reorder_stored_screen_sets(web_context.admin_screen.id, data['item'])
                case _:
                    raise ValueError(f'action=[{action}]')
            event_database.commit()
        event_loader.clear_cache(event_uniq_id)
        return self._admin_event_screens_render(
            request, event_uniq_id=event_uniq_id, modal='screen_sets', screen_id=screen_id,
            screen_set_id=next_screen_set_id)

    @post(
        path='/admin/screen-set-add/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-set-add',
    )
    async def htmx_admin_screen_set_add(
            self, request: HTMXRequest,
            event_uniq_id: str,
            screen_id: int,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
    ) -> Template | ClientRedirect:
        return self._admin_screen_sets_update(
            request, event_uniq_id=event_uniq_id, action='add', screen_id=screen_id, screen_set_id=None, data=data)

    @post(
        path='/admin/screen-set-clone/{event_uniq_id:str}/{screen_id:int}/{screen_set_id:int}',
        name='admin-screen-set-clone',
    )
    async def htmx_admin_screen_set_clone(
            self, request: HTMXRequest,
            event_uniq_id: str,
            screen_id: int,
            screen_set_id: int,
            data: Annotated[dict[str, str | list[int]], Body(media_type=RequestEncodingType.URL_ENCODED), ],
    ) -> Template | ClientRedirect:
        return self._admin_screen_sets_update(
            request, event_uniq_id=event_uniq_id, action='clone', screen_id=screen_id, screen_set_id=screen_set_id,
            data=data)

    @patch(
        path='/admin/screen-set-update/{event_uniq_id:str}/{screen_id:int}/{screen_set_id:int}',
        name='admin-screen-set-update',
    )
    async def htmx_admin_screen_set_update(
            self, request: HTMXRequest,
            event_uniq_id: str,
            screen_id: int,
            screen_set_id: int,
            data: Annotated[dict[str, str | list[int]], Body(media_type=RequestEncodingType.URL_ENCODED), ],
    ) -> Template | ClientRedirect:
        return self._admin_screen_sets_update(
            request, event_uniq_id=event_uniq_id, action='update', screen_id=screen_id, screen_set_id=screen_set_id,
            data=data)

    @delete(
        path='/admin/screen-set-delete/{event_uniq_id:str}/{screen_id:int}/{screen_set_id:int}',
        name='admin-screen-set-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_screen_set_delete(
            self, request: HTMXRequest,
            data: Annotated[dict[str, str | list[int]], Body(media_type=RequestEncodingType.URL_ENCODED), ],
            event_uniq_id: str,
            screen_id: int,
            screen_set_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_screen_sets_update(
            request, event_uniq_id=event_uniq_id, action='delete', screen_id=screen_id, screen_set_id=screen_set_id,
            data=data)

    @patch(
        path='/admin/screen-reorder-sets/{event_uniq_id:str}/{screen_id:int}',
        name='admin-screen-reorder-sets',
    )
    async def htmx_admin_screen_reorder_sets(
            self, request: HTMXRequest,
            event_uniq_id: str,
            screen_id: int,
            data: Annotated[dict[str, str | list[int]], Body(media_type=RequestEncodingType.URL_ENCODED), ],
    ) -> Template | ClientRedirect:
        return self._admin_screen_sets_update(
            request, event_uniq_id=event_uniq_id, action='reorder', screen_id=screen_id, screen_set_id=None,
            data=data)
