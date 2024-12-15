from logging import Logger
from typing import Annotated, Any

from litestar import get, delete, patch, post
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common.logger import get_logger
from data.chessevent import ChessEvent
from data.loader import EventLoader
from database.sqlite import EventDatabase
from database.store import StoredChessEvent
from web.controllers.admin.event_admin_controller import EventAdminWebContext, AbstractEventAdminController
from web.controllers.index_controller import WebContext
from web.messages import Message

logger: Logger = get_logger()


class ChessEventAdminWebContext(EventAdminWebContext):
    def __init__(
            self, request: HTMXRequest,
            event_uniq_id: str,
            admin_event_tab: str | None,
            chessevent_id: int | None,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ] | None,
    ):
        super().__init__(request, data=data, event_uniq_id=event_uniq_id, admin_event_tab=admin_event_tab)
        self.admin_chessevent: ChessEvent | None = None
        if chessevent_id:
            try:
                self.admin_chessevent = self.admin_event.chessevents_by_id[chessevent_id]
            except KeyError:
                self._redirect_error(f'La connexion à ChessEvent [{chessevent_id}] n\'existe pas')
                return

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_chessevent': self.admin_chessevent,
        }


class ChessEventAdminController(AbstractEventAdminController):

    @staticmethod
    def _admin_validate_chessevent_update_data(
            action: str,
            web_context: ChessEventAdminWebContext,
            data: dict[str, str] | None = None,
    ) -> StoredChessEvent:
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        uniq_id: str = WebContext.form_data_to_str(data, 'uniq_id')
        match action:
            case 'create':
                if not uniq_id:
                    errors['uniq_id'] = 'Veuillez entrer l\'identifiant de la connexion à ChessEvent.'
                elif uniq_id in web_context.admin_event.chessevents_by_uniq_id:
                    errors['uniq_id'] = f'La connexion à ChessEvent [{uniq_id}] existe déjà.'
            case 'update':
                if not uniq_id:
                    errors['uniq_id'] = 'Veuillez entrer l\'identifiant de la connexion à ChessEvent.'
                elif uniq_id != web_context.admin_chessevent.uniq_id \
                        and uniq_id in web_context.admin_event.chessevents_by_uniq_id:
                    errors['uniq_id'] = \
                        f'Une autre connexion à ChessEvent avec l\'identifiant [{uniq_id}] existe déjà.'
            case 'delete':
                pass
            case _:
                raise ValueError(f'action=[{action}]')
        user_id: str = WebContext.form_data_to_str(data, 'user_id')
        password: str = WebContext.form_data_to_str(data, 'password')
        event_id: str = WebContext.form_data_to_str(data, 'event_id')
        match action:
            case 'create' | 'update':
                if not user_id:
                    errors['user_id'] = 'Veuillez entrer l\'identifiant de connexion à ChessEvent.'
                if not password:
                    errors['password'] = 'Veuillez entrer le mot de passe de connexion à ChessEvent.'
                if not event_id:
                    errors['event_id'] = 'Veuillez entrer le nom de l\'évènement ChessEvent.'
            case 'delete':
                pass
            case _:
                raise ValueError(f'action=[{action}]')
        return StoredChessEvent(
            id=web_context.admin_chessevent.id if action != 'create' else None,
            uniq_id=uniq_id,
            user_id=user_id,
            password=password,
            event_id=event_id,
            errors=errors,
        )

    @classmethod
    def _admin_event_chessevents_render(
            cls, request: HTMXRequest,
            event_uniq_id: str,
            modal: str | None = None,
            action: str | None = None,
            chessevent_id: int | None = None,
            data: dict[str, str] | None = None,
            errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: ChessEventAdminWebContext = ChessEventAdminWebContext(
            request, event_uniq_id=event_uniq_id, admin_event_tab='chessevents', chessevent_id=chessevent_id, data=None)
        if web_context.error:
            return web_context.error
        template_context: dict[str, Any] = cls._get_admin_event_render_context(web_context)
        match modal:
            case None:
                pass
            case 'chessevent':
                if data is None:
                    data: dict[str, str] = {}
                    match action:
                        case 'update':
                            data['uniq_id'] = WebContext.value_to_form_data(
                                web_context.admin_chessevent.stored_chessevent.uniq_id)
                            data['event_id'] = WebContext.value_to_form_data(
                                web_context.admin_chessevent.stored_chessevent.event_id)
                            data['user_id'] = WebContext.value_to_form_data(
                                web_context.admin_chessevent.stored_chessevent.user_id)
                            data['password'] = WebContext.value_to_form_data(
                                web_context.admin_chessevent.stored_chessevent.password)
                        case 'create':
                            data['uniq_id'] = ''
                            data['uniq_id'] = ''
                            data['event_id'] = ''
                            data['user_id'] = ''
                            data['password'] = ''
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    stored_chessevent: StoredChessEvent = cls._admin_validate_chessevent_update_data(
                        action, web_context, data)
                    errors = stored_chessevent.errors
                if errors is None:
                    errors = {}
                template_context |= {
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case _:
                raise ValueError(f'modal=[{modal}]')
        return cls._admin_event_render(template_context)

    @get(
        path='/admin/chessevent-modal/create/{event_uniq_id:str}',
        name='admin-chessevent-create-modal',
        cache=1,
    )
    async def htmx_admin_chessevent_create_modal(
            self, request: HTMXRequest,
            event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_chessevents_render(
            request, event_uniq_id=event_uniq_id, modal='chessevent', action='create', chessevent_id=None)

    @get(
        path='/admin/chessevent-modal/{action:str}/{event_uniq_id:str}/{chessevent_id:int}',
        name='admin-chessevent-modal',
        cache=1,
    )
    async def htmx_admin_chessevent_modal(
            self, request: HTMXRequest,
            event_uniq_id: str,
            action: str,
            chessevent_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_chessevents_render(
            request, event_uniq_id=event_uniq_id, modal='chessevent', action=action, chessevent_id=chessevent_id)

    def _admin_chessevent_update(
            self, request: HTMXRequest,
            event_uniq_id: str,
            action: str,
            chessevent_id: int | None,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
    ) -> Template | ClientRedirect:
        match action:
            case 'update' | 'delete' | 'create':
                web_context: ChessEventAdminWebContext = ChessEventAdminWebContext(
                    request, event_uniq_id=event_uniq_id, admin_event_tab='chessevents', chessevent_id=chessevent_id,
                    data=data)
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        stored_chessevent: StoredChessEvent = self._admin_validate_chessevent_update_data(action, web_context, data)
        if stored_chessevent.errors:
            return self._admin_event_chessevents_render(
                request, action=action, event_uniq_id=event_uniq_id, chessevent_id=chessevent_id, data=data,
                errors=stored_chessevent.errors)
        event_loader: EventLoader = EventLoader.get(request=request)
        with EventDatabase(web_context.admin_event.uniq_id, write=True) as event_database:
            match action:
                case 'create':
                    stored_chessevent = event_database.add_stored_chessevent(stored_chessevent)
                    event_database.commit()
                    Message.success(request, f'La connexion à ChessEvent [{stored_chessevent.uniq_id}] a été créée.')
                    event_loader.clear_cache(event_uniq_id)
                    return self._admin_event_chessevents_render(request, event_uniq_id=event_uniq_id)
                case 'update':
                    stored_chessevent = event_database.update_stored_chessevent(stored_chessevent)
                    event_database.commit()
                    Message.success(request, f'La connexion à ChessEvent [{stored_chessevent.uniq_id}] a été modifiée.')
                    event_loader.clear_cache(event_uniq_id)
                    return self._admin_event_chessevents_render(request, event_uniq_id=event_uniq_id)
                case 'delete':
                    event_database.delete_stored_chessevent(web_context.admin_chessevent.id)
                    event_database.commit()
                    Message.success(
                        request, f'La connexion à ChessEvent [{web_context.admin_chessevent.uniq_id}] a été supprimée.')
                    event_loader.clear_cache(event_uniq_id)
                    return self._admin_event_chessevents_render(request, event_uniq_id=event_uniq_id)
                case _:
                    raise ValueError(f'action=[{action}]')

    @post(
        path='/admin/chessevent-create/{event_uniq_id:str}',
        name='admin-chessevent-create'
    )
    async def htmx_admin_chessevent_create(
            self, request: HTMXRequest,
            event_uniq_id: str,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
    ) -> Template | ClientRedirect:
        return self._admin_chessevent_update(
            request, event_uniq_id=event_uniq_id, action='create', chessevent_id=None, data=data)

    @post(
        path='/admin/chessevent-clone/{event_uniq_id:str}/{chessevent_id:int}',
        name='admin-chessevent-clone'
    )
    async def htmx_admin_chessevent_clone(
            self, request: HTMXRequest,
            event_uniq_id: str,
            chessevent_id: int | None,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
    ) -> Template | ClientRedirect:
        web_context: ChessEventAdminWebContext = ChessEventAdminWebContext(
            request, event_uniq_id=event_uniq_id, admin_event_tab='chessevents', chessevent_id=chessevent_id,
            data=data)
        with EventDatabase(web_context.admin_event.uniq_id, write=True) as event_database:
            stored_chessevent = event_database.clone_stored_chessevent(web_context.admin_chessevent.id)
            event_database.commit()
            Message.success(
                request,
                f'La connexion à ChessEvent [{web_context.admin_chessevent.uniq_id}] a été dupliquée '
                f'([{stored_chessevent.uniq_id}]).')
        EventLoader.get(request=request).clear_cache(event_uniq_id)
        return self._admin_event_chessevents_render(
            request, modal='chessevent', action='update', event_uniq_id=event_uniq_id,
            chessevent_id=stored_chessevent.id)

    @patch(
        path='/admin/chessevent-update/{event_uniq_id:str}/{chessevent_id:int}',
        name='admin-chessevent-update'
    )
    async def htmx_admin_chessevent_update(
            self, request: HTMXRequest,
            event_uniq_id: str,
            chessevent_id: int | None,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
    ) -> Template | ClientRedirect:
        return self._admin_chessevent_update(
            request, event_uniq_id=event_uniq_id, action='update', chessevent_id=chessevent_id, data=data)

    @delete(
        path='/admin/chessevent-delete/{event_uniq_id:str}/{chessevent_id:int}',
        name='admin-chessevent-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_chessevent_delete(
            self, request: HTMXRequest,
            event_uniq_id: str,
            chessevent_id: int | None,
            data: Annotated[dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED), ],
    ) -> Template | ClientRedirect:
        return self._admin_chessevent_update(
            request, event_uniq_id=event_uniq_id, action='delete', chessevent_id=chessevent_id, data=data)
