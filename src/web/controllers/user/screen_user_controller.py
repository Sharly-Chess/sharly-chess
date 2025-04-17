from contextlib import suppress
from typing import Annotated

from litestar import head, post, get
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import Reswap, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_304_NOT_MODIFIED

from common.i18n import _
from data.screen_set import ScreenSet
from data.tournament import Tournament
from utils.enum import ScreenType
from web.controllers.user.base_screen_user_controller import (
    BaseScreenUserController,
    BasicScreenOrFamilyUserWebContext,
    RotatorUserWebContext,
    ScreenUserWebContext,
)
from web.messages import Message
from web.session import SessionHandler


class LoginUserWebContext(ScreenUserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        screen_uniq_id: str | None,
    ):
        super().__init__(
            request,
            data=data,
            event_uniq_id=event_uniq_id,
            screen_uniq_id=screen_uniq_id,
            screen_needed=True,
        )
        field = 'password'
        self.password: str = self._form_data_to_str(field, None) or ''
        if self.password is None:
            self._redirect_error('Missing password.')


class ScreenUserController(BaseScreenUserController):
    @post(
        path='/user/login/{event_uniq_id:str}/{screen_uniq_id:str}',
        name='user-login',
    )
    async def htmx_user_login(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        screen_uniq_id: str,
    ) -> Template | ClientRedirect:
        web_context: LoginUserWebContext = LoginUserWebContext(
            request,
            data=data,
            event_uniq_id=event_uniq_id,
            screen_uniq_id=screen_uniq_id,
        )
        if web_context.error:
            return web_context.error
        if web_context.user_event is None:
            raise RuntimeError('user_event not defined')
        if data['password'] == web_context.user_event.update_password:
            Message.success(request, _('Authentication successful!'))
            SessionHandler.store_password(
                request, web_context.user_event, web_context.password
            )
            return self._user_screen_render(web_context)
        if data['password'] == '':
            Message.warning(request, _('Please enter the password.'))
        else:
            Message.error(request, _('Incorrect password.'))
            SessionHandler.store_password(request, web_context.user_event, None)
        return self.render_messages(request)

    @staticmethod
    def _user_screen_set_refresh_needed(
        screen_set: ScreenSet,
        date: float,
    ) -> bool:
        tournament: Tournament = screen_set.tournament
        if tournament.last_update > date:
            if tournament.last_update > date:
                return True
        if tournament.last_check_in_update > date:
            return True
        match screen_set.type:
            case ScreenType.BOARDS | ScreenType.INPUT | ScreenType.RANKING:
                if tournament.last_illegal_move_update > date:
                    return True
                if tournament.last_result_update > date:
                    return True
            case ScreenType.PLAYERS:
                pass
            case _:
                raise ValueError(f'type={screen_set.type}')
        with suppress(FileNotFoundError):
            if tournament.file.lstat().st_mtime > date:
                return True
        return False

    @classmethod
    def _user_screen_refresh_needed(
        cls,
        web_context: BasicScreenOrFamilyUserWebContext,
        date: float,
    ) -> bool:
        if web_context.screen:
            assert web_context.screen.event is not None
            if (
                web_context.screen.event.last_update
                and web_context.screen.event.last_update > date
            ):
                return True
            if web_context.screen.last_update > date:
                return True
            match web_context.screen.type:
                case ScreenType.IMAGE:
                    pass
                case (
                    ScreenType.BOARDS
                    | ScreenType.INPUT
                    | ScreenType.PLAYERS
                    | ScreenType.RANKING
                ):
                    for screen_set in web_context.screen.screen_sets_by_id.values():
                        if cls._user_screen_set_refresh_needed(screen_set, date):
                            return True
                case ScreenType.RESULTS:
                    assert web_context.screen.event is not None
                    results_tournament_ids: list[int] = (
                        web_context.screen.results_tournament_ids
                        if web_context.screen.results_tournament_ids
                        else list(web_context.screen.event.tournaments_by_id.keys())
                    )
                    for tournament_id in results_tournament_ids:
                        with suppress(KeyError):
                            tournament: Tournament = (
                                web_context.screen.event.tournaments_by_id[
                                    tournament_id
                                ]
                            )
                            if tournament.last_update > date:
                                return True
                            if tournament.last_result_update > date:
                                return True
                case _:
                    raise ValueError(f'type={web_context.screen.type}')
        else:
            assert web_context.family is not None
            assert web_context.family.event is not None
            if (
                web_context.family.event.last_update
                and web_context.family.event.last_update > date
            ):
                return True
            if web_context.family.last_update and web_context.family.last_update > date:
                return True
        return False

    @get(
        path='/user/screen/{event_uniq_id:str}/{screen_uniq_id:str}',
        name='user-screen',
    )
    async def htmx_user_screen(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_uniq_id: str,
    ) -> Template | Reswap | ClientRedirect:
        web_context: BasicScreenOrFamilyUserWebContext = (
            BasicScreenOrFamilyUserWebContext(
                request,
                data=None,
                event_uniq_id=event_uniq_id,
                screen_uniq_id=screen_uniq_id,
            )
        )
        if web_context.error:
            return web_context.error
        date: float | None = self.get_if_modified_since(request)
        if date is None or self._user_screen_refresh_needed(web_context, date):
            return self._user_screen_render(web_context)
        else:
            return Reswap(
                content=None, method='none', status_code=HTTP_304_NOT_MODIFIED
            )

    @head(
        path='/user/screen/{event_uniq_id:str}/{screen_uniq_id:str}',
        name='user-screen-head',
        status_code=HTTP_304_NOT_MODIFIED,
    )
    async def htmx_user_screen_head(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        screen_uniq_id: str,
    ) -> None:
        pass

    @get(
        path=[
            '/user/rotator/{event_uniq_id:str}/{rotator_id:int}/{rotator_screen_index:int}',
            '/user/rotator/{event_uniq_id:str}/{rotator_id:int}',
        ],
        name='user-rotator',
    )
    async def htmx_user_rotator(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        rotator_id: int,
        rotator_screen_index: int = 0,
    ) -> Template | ClientRedirect:
        web_context: RotatorUserWebContext = RotatorUserWebContext(
            request,
            data=None,
            event_uniq_id=event_uniq_id,
            rotator_id=rotator_id,
            rotator_screen_index=rotator_screen_index,
        )
        if web_context.error:
            return web_context.error
        return self._user_screen_render(web_context)

    @head(
        path=[
            '/user/rotator/{event_uniq_id:str}/{rotator_id:int}/{rotator_screen_index:int}',
            '/user/rotator/{event_uniq_id:str}/{rotator_id:int}',
        ],
        name='user-rotator-head',
        status_code=HTTP_304_NOT_MODIFIED,
    )
    async def htmx_user_rotator_head(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        rotator_id: int,
        rotator_screen_index: int = 0,
    ) -> None:
        pass
