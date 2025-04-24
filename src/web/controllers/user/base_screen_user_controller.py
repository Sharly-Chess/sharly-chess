from logging import Logger
from typing import Annotated, Any, Iterable

from litestar.plugins.htmx import HTMXRequest, HTMXTemplate, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template

from common.i18n import _
from common.logger import get_logger
from common.papi_web_config import PapiWebConfig
from data.client_controller import ClientController
from data.family import Family
from data.rotator import Rotator
from data.screen import Screen
from utils.enum import ScreenType
from plugins.manager import plugin_manager
from plugins.utils import ExtraColumn
from web.controllers.user.event_user_controller import EventUserWebContext
from web.controllers.user.base_user_controller import BaseUserController
from web.messages import Message
from web.session import SessionHandler

logger: Logger = get_logger()


class ScreenOrRotatorUserWebContext(EventUserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ]
        | None,
        event_uniq_id: str,
        screen_uniq_id: str | None,
        rotator_id: int | None,
        rotator_screen_index: int | None,
        client_controller_id: int | None,
    ):
        super().__init__(
            request, data=data, event_uniq_id=event_uniq_id, user_event_tab=None
        )
        self.screen: Screen | None = None
        self.rotator: Rotator | None = None
        self.rotator_screen_index: int | None = rotator_screen_index or 0
        self.client_controller: ClientController | None = None
        if self.error:
            return
        assert self.user_event is not None
        if screen_uniq_id:
            try:
                self.screen = self.user_event.screens_by_uniq_id[screen_uniq_id]
            except KeyError:
                self._redirect_error(f'Screen [{screen_uniq_id}] not found.')
                return
            if not self.screen.public and not self.admin_auth:
                self._redirect_error(
                    f'Access denied for screen [{self.screen.uniq_id}].'
                )
                return
            self.user_event_tab = self.screen.type.value
        elif rotator_id:
            assert rotator_id is not None
            try:
                self.rotator = self.user_event.rotators_by_id[rotator_id]
            except KeyError:
                self._redirect_error(f'Rotator [{rotator_id}] not found.')
                return
            if not self.rotator.public and not self.admin_auth:
                self._redirect_error(
                    f'Access denied for rotator [{self.rotator.uniq_id}].'
                )
                return
            self.rotator_screen_index = self.rotator_screen_index % len(
                self.rotator.rotating_screens
            )
            self.screen = self.rotator.rotating_screens[self.rotator_screen_index]
            self.user_event_tab = 'rotators'
        else:
            assert client_controller_id is not None
            try:
                self.client_controller = self.user_event.client_controllers_by_id[
                    client_controller_id
                ]
            except KeyError:
                self._redirect_error(
                    f'Client controller [{client_controller_id}] not found.'
                )
                return

            if rotator := self.client_controller.rotator:
                self.rotator_screen_index = self.rotator_screen_index % len(
                    rotator.rotating_screens
                )
                self.screen = rotator.rotating_screens[self.rotator_screen_index]
            else:
                self.screen = self.client_controller.screen

            self.user_event_tab = 'client_controllers'

    @property
    def login_needed(self) -> bool:
        assert self.user_event is not None
        if self.screen is not None:
            if self.screen.type != ScreenType.INPUT:
                return False
        if not self.user_event.update_password:
            return False
        session_password: str | None = SessionHandler.get_stored_password(
            self.request, self.user_event
        )
        logger.debug('session_password=%s', '*' * (8 if session_password else 0))
        if session_password is None:
            Message.error(
                self.request, _('Access denied, please authenticate to enter results.')
            )
            return True
        if session_password != self.user_event.update_password:
            Message.error(self.request, _('Incorrect password.'))
            SessionHandler.store_password(self.request, self.user_event, None)
            return True
        return False

    @property
    def background_image(self) -> str | None:
        return self.screen.background_image if self.screen else None

    @property
    def background_color(self) -> str:
        return (
            self.screen.background_color
            if self.screen
            else PapiWebConfig.default_background_color
        )

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'rotator': self.rotator,
            'rotator_screen_index': self.rotator_screen_index,
            'screen': self.screen,
            'client_controller': self.client_controller,
            'login_needed': self.login_needed,
        }


class ScreenUserWebContext(ScreenOrRotatorUserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ]
        | None,
        event_uniq_id: str,
        screen_uniq_id: str | None,
        screen_needed: bool,
    ):
        super().__init__(
            request,
            data=data,
            event_uniq_id=event_uniq_id,
            screen_uniq_id=screen_uniq_id,
            rotator_id=None,
            rotator_screen_index=None,
            client_controller_id=None,
        )
        if self.error:
            return
        if screen_needed and not self.screen:
            self._redirect_error('Screen is mandatory.')
            return


class RotatorUserWebContext(ScreenOrRotatorUserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str] | None,
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        rotator_id: int,
        rotator_screen_index: int,
    ):
        super().__init__(
            request,
            data=data,
            event_uniq_id=event_uniq_id,
            screen_uniq_id=None,
            rotator_id=rotator_id,
            rotator_screen_index=rotator_screen_index,
            client_controller_id=None,
        )


class ClientControllerUserWebContext(ScreenOrRotatorUserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str] | None,
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        client_controller_id: int,
        rotator_screen_index: int = 0,
    ):
        super().__init__(
            request,
            data=data,
            event_uniq_id=event_uniq_id,
            screen_uniq_id=None,
            rotator_id=None,
            rotator_screen_index=rotator_screen_index,
            client_controller_id=client_controller_id,
        )


class BasicScreenOrFamilyUserWebContext(ScreenUserWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str] | None,
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
        assert self.screen is not None
        assert self.user_event is not None
        self.family: Family | None = None
        if self.error:
            return
        if ':' in self.screen.uniq_id:
            family_uniq_id: str = self.screen.uniq_id.split(':')[0]
            try:
                self.family = self.user_event.families_by_uniq_id[family_uniq_id]
            except KeyError:
                self._redirect_error(f'Family [{family_uniq_id}] not found.')
                return

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'family': self.family,
        }


class BaseScreenUserController(BaseUserController):
    @classmethod
    def _user_screen_render(
        cls,
        web_context: ScreenOrRotatorUserWebContext,
    ) -> Template | ClientRedirect:
        # Allow plugin to provide extra columns
        per_plugin_columns: Iterable[Iterable[ExtraColumn]] = []
        if web_context.screen is not None:
            per_plugin_columns: Iterable[Iterable[ExtraColumn]] = (
                plugin_manager.hook.get_extra_screen_columns(
                    screen=web_context.screen.type
                )
            )
        extra_columns: dict[str, list[ExtraColumn]] = {}
        for plugin_columns in per_plugin_columns:
            for extra_column in plugin_columns:
                c = extra_columns.setdefault(extra_column.at, [])
                c.append(extra_column)
        if web_context.screen and web_context.screen.type == ScreenType.RANKING:
            for tournament in {
                screen_set.tournament
                for screen_set in web_context.screen.screen_sets_sorted_by_order
            }:
                tournament.compute_player_ranks(
                    after_round=web_context.screen.ranking_round
                )
        return HTMXTemplate(
            template_name='user/screen.html',
            context=web_context.template_context
            | {
                'last_result_updated': SessionHandler.get_session_last_result_updated(
                    web_context.request
                ),
                'last_illegal_move_updated': SessionHandler.get_session_user_last_illegal_move_updated(
                    web_context.request
                ),
                'last_check_in_updated': SessionHandler.get_session_user_last_check_in_updated(
                    web_context.request
                ),
                'messages': Message.messages(web_context.request),
                'extra_columns': extra_columns,
            },
        )
