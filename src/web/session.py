import logging
import time
from typing import TYPE_CHECKING, Any, Callable, Sequence

from litestar.contrib.htmx.request import HTMXRequest

from common import get_logger
from common.papi_web_config import PapiWebConfig
from data.player import Federation, Club
from data.util import PlayerGender, PlayerCategory

if TYPE_CHECKING:
    from data.event import Event

logger: logging.Logger = get_logger()


class SessionHandler:
    AUTH_SESSION_KEY: str = 'auth'

    @classmethod
    def store_password(cls, request: HTMXRequest, event: 'Event', password: str | None):
        if cls.AUTH_SESSION_KEY not in request.session:
            request.session[cls.AUTH_SESSION_KEY] = {}
        request.session[cls.AUTH_SESSION_KEY][event.uniq_id] = password

    @classmethod
    def get_stored_password(cls, request: HTMXRequest, event: 'Event') -> str | None:
        try:
            return request.session[cls.AUTH_SESSION_KEY][event.uniq_id]
        except KeyError:
            return None

    LAST_RESULT_UPDATED_SESSION_KEY: str = 'last_result_updated'

    @classmethod
    def set_session_last_result_updated(
        cls,
        request: HTMXRequest,
        tournament_id: int,
        round_: int,
        board_id: int,
    ):
        request.session[cls.LAST_RESULT_UPDATED_SESSION_KEY] = {
            'tournament_id': tournament_id,
            'round': round_,
            'board_id': board_id,
            'expiration': time.time() + 20,
        }

    @classmethod
    def get_session_last_result_updated(cls, request: HTMXRequest):
        return request.session.get(cls.LAST_RESULT_UPDATED_SESSION_KEY, None)

    USER_LAST_ILLEGAL_MOVE_UPDATED_KEY: str = 'user_last_illegal_move_updated'

    @classmethod
    def set_session_user_last_illegal_move_updated(
        cls,
        request: HTMXRequest,
        tournament_id: int,
        player_id: int,
    ):
        request.session[cls.USER_LAST_ILLEGAL_MOVE_UPDATED_KEY] = {
            'tournament_id': tournament_id,
            'player_id': player_id,
            'expiration': time.time() + 20,
        }

    @classmethod
    def get_session_user_last_illegal_move_updated(cls, request: HTMXRequest):
        return request.session.get(cls.USER_LAST_ILLEGAL_MOVE_UPDATED_KEY, None)

    USER_LAST_CHECK_IN_UPDATED_KEY: str = 'user_last_check_in_updated'

    @classmethod
    def set_session_user_last_check_in_updated(
        cls,
        request: HTMXRequest,
        tournament_id: int,
        player_id: int,
    ):
        request.session[cls.USER_LAST_CHECK_IN_UPDATED_KEY] = {
            'tournament_id': tournament_id,
            'player_id': player_id,
            'expiration': time.time() + 20,
        }

    @classmethod
    def get_session_user_last_check_in_updated(cls, request: HTMXRequest):
        return request.session.get(cls.USER_LAST_CHECK_IN_UPDATED_KEY, None)

    ADMIN_SCREENS_SHOW_FAMILY_SCREENS_KEY: str = 'admin_screens_show_family_screens'

    @classmethod
    def set_session_admin_screens_show_family_screens(
        cls, request: HTMXRequest, b: bool
    ):
        request.session[cls.ADMIN_SCREENS_SHOW_FAMILY_SCREENS_KEY] = b

    @classmethod
    def get_session_admin_screens_show_family_screens(
        cls, request: HTMXRequest
    ) -> bool:
        return request.session.get(cls.ADMIN_SCREENS_SHOW_FAMILY_SCREENS_KEY, False)

    ADMIN_SCREENS_SHOW_DETAILS_KEY: str = 'admin_screens_show_details'

    @classmethod
    def set_session_admin_screens_show_details(cls, request: HTMXRequest, b: bool):
        request.session[cls.ADMIN_SCREENS_SHOW_DETAILS_KEY] = b

    @classmethod
    def get_session_admin_screens_show_details(cls, request: HTMXRequest) -> bool:
        return request.session.get(cls.ADMIN_SCREENS_SHOW_DETAILS_KEY, False)

    ADMIN_FAMILIES_SHOW_DETAILS_KEY: str = 'admin_families_show_details'

    @classmethod
    def set_session_admin_families_show_details(cls, request: HTMXRequest, b: bool):
        request.session[cls.ADMIN_FAMILIES_SHOW_DETAILS_KEY] = b

    @classmethod
    def get_session_admin_families_show_details(cls, request: HTMXRequest) -> bool:
        return request.session.get(cls.ADMIN_FAMILIES_SHOW_DETAILS_KEY, False)

    ADMIN_ROTATORS_SHOW_DETAILS_KEY: str = 'admin_rotators_show_details'

    @classmethod
    def set_session_admin_rotators_show_details(cls, request: HTMXRequest, b: bool):
        request.session[cls.ADMIN_ROTATORS_SHOW_DETAILS_KEY] = b

    @classmethod
    def get_session_admin_rotators_show_details(cls, request: HTMXRequest) -> bool:
        return request.session.get(cls.ADMIN_ROTATORS_SHOW_DETAILS_KEY, False)

    ADMIN_TOURNAMENTS_SHOW_DETAILS_KEY: str = 'admin_tournaments_show_details'

    @classmethod
    def set_session_admin_tournaments_show_details(cls, request: HTMXRequest, b: bool):
        request.session[cls.ADMIN_TOURNAMENTS_SHOW_DETAILS_KEY] = b

    @classmethod
    def get_session_admin_tournaments_show_details(cls, request: HTMXRequest) -> bool:
        return request.session.get(cls.ADMIN_TOURNAMENTS_SHOW_DETAILS_KEY, False)

    ADMIN_EVENTS_SHOW_DETAILS_KEY: str = 'admin_events_show_details'

    @classmethod
    def set_session_admin_events_show_details(cls, request: HTMXRequest, b: bool):
        request.session[cls.ADMIN_EVENTS_SHOW_DETAILS_KEY] = b

    @classmethod
    def get_session_admin_events_show_details(cls, request: HTMXRequest) -> bool:
        return request.session.get(cls.ADMIN_EVENTS_SHOW_DETAILS_KEY, False)

    ADMIN_SCREENS_SCREEN_TYPES_KEY: str = 'admin_screens_screen_types'

    @classmethod
    def set_session_admin_screens_screen_types(
        cls, request: HTMXRequest, screen_types: set[str]
    ):
        request.session[cls.ADMIN_SCREENS_SCREEN_TYPES_KEY] = list(screen_types)

    @classmethod
    def get_session_admin_screens_screen_types(cls, request: HTMXRequest) -> set[str]:
        return set(request.session.get(
            cls.ADMIN_SCREENS_SCREEN_TYPES_KEY,
            ['boards', 'input', 'players', 'results', 'ranking', 'image', ],
        ))

    LOCALE_KEY: str = 'locale'

    @classmethod
    def set_session_locale(cls, request: HTMXRequest, locale: str):
        request.session[cls.LOCALE_KEY] = locale

    @classmethod
    def get_session_locale(cls, request: HTMXRequest) -> str:
        return request.session.get(cls.LOCALE_KEY, PapiWebConfig().locale)
    
    @classmethod
    def set_session_data_from_query_params(
        cls,
        request: HTMXRequest,
        data: dict[
            str,
            tuple[
                Sequence[str | int] | str | int | None,  # query param(s)
                Callable[[str | int], Any] | None,   # transform
                Callable[[str | int], bool] | None   # condition
            ]
        ]
    ):
        for key, (query_params, transform, condition) in data.items():
            if transform is None:
                transform = lambda x: x
            if condition is None:
                condition = lambda x: x # '' must be ignored
                
            if query_params is not None:
                if isinstance(query_params, str | int) and condition(query_params):
                    request.session[key] = transform(query_params)
                elif isinstance(query_params, list) :
                    request.session[key] = [
                        transform(query_param)
                        for query_param in query_params
                        if condition(query_param)
                    ]

    @classmethod
    def get_session_data(cls, request: HTMXRequest, items: list[tuple[str, Any, Callable[[Any], Any] | None]]):
        data = []
        for key, value, transform in items:
            session_data = request.session.get(key, value)
            if transform and isinstance(session_data, list):
                data.append([transform(item) for item in session_data])
            else:
                data.append(transform(session_data) if transform else session_data)
        return data
