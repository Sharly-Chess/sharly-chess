import logging
import time
from typing import TYPE_CHECKING

from litestar.contrib.htmx.request import HTMXRequest

from common import get_logger
from common.papi_web_config import PapiWebConfig
from data.player import Federation, Club
from utils.enum import PlayerGender, PlayerCategory

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
        return set(
            request.session.get(
                cls.ADMIN_SCREENS_SCREEN_TYPES_KEY,
                [
                    'boards',
                    'input',
                    'players',
                    'results',
                    'ranking',
                    'image',
                ],
            )
        )

    LOCALE_KEY: str = 'locale'

    @classmethod
    def set_session_locale(cls, request: HTMXRequest, locale: str):
        request.session[cls.LOCALE_KEY] = locale

    @classmethod
    def get_session_locale(cls, request: HTMXRequest) -> str:
        return request.session.get(cls.LOCALE_KEY, PapiWebConfig().locale)

    ADMIN_PLAYERS_SORT_KEY: str = 'admin_players_sort'

    @classmethod
    def set_session_admin_players_sort(cls, request: HTMXRequest, players_sort: str):
        assert players_sort in [
            'alpha',
            'rating_desc',
            'rating_asc',
            'yob_desc',
            'yob_asc',
            'category_desc',
            'category_asc',
            'club',
            'tournament',
        ]
        request.session[cls.ADMIN_PLAYERS_SORT_KEY] = players_sort

    @classmethod
    def get_session_admin_players_sort(cls, request: HTMXRequest) -> str:
        return request.session.get(cls.ADMIN_PLAYERS_SORT_KEY, 'alpha')

    ADMIN_PLAYERS_FILTER_COLUMNS_KEY: str = 'admin_players_filter_columns'

    @classmethod
    def set_session_admin_players_filter_columns(
        cls, request: HTMXRequest, columns: list[str]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_COLUMNS_KEY] = columns

    @classmethod
    def get_session_admin_players_filter_columns(
        cls, request: HTMXRequest
    ) -> list[str]:
        return request.session.get(
            cls.ADMIN_PLAYERS_FILTER_COLUMNS_KEY,
            PapiWebConfig.default_players_filter_columns,
        )

    ADMIN_PLAYERS_FILTER_FEDERATIONS_KEY: str = 'admin_players_filter_federations'

    @classmethod
    def set_session_admin_players_filter_federations(
        cls, request: HTMXRequest, federations: list[Federation]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_FEDERATIONS_KEY] = federations

    @classmethod
    def get_session_admin_players_filter_federations(
        cls, request: HTMXRequest
    ) -> list[Federation]:
        # type-casting is needed because the value returned by Session.get is serialized
        # when stored from a previous request (and kept as-is if stored by the current request)
        return [
            d if isinstance(d, Federation) else Federation(d)
            for d in request.session.get(cls.ADMIN_PLAYERS_FILTER_FEDERATIONS_KEY, [])
        ]

    ADMIN_PLAYERS_FILTER_CLUBS_KEY: str = 'admin_players_filter_clubs'

    @classmethod
    def set_session_admin_players_filter_clubs(
        cls, request: HTMXRequest, clubs: list[Club]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_CLUBS_KEY] = clubs

    @classmethod
    def get_session_admin_players_filter_clubs(cls, request: HTMXRequest) -> list[Club]:
        # type-casting is needed because the value returned by Session.get is serialized
        # when stored from a previous request (and kept as-is if stored by the current request)
        return [
            d if isinstance(d, Club) else Club(d)
            for d in request.session.get(cls.ADMIN_PLAYERS_FILTER_CLUBS_KEY, [])
        ]

    ADMIN_PLAYERS_FILTER_CLUBS_SEARCH_KEY: str = 'admin_players_filter_clubs_search'

    @classmethod
    def set_session_admin_players_filter_clubs_search(
        cls, request: HTMXRequest, origin: str
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_CLUBS_SEARCH_KEY] = origin

    @classmethod
    def get_session_admin_players_filter_clubs_search(cls, request: HTMXRequest) -> str:
        return request.session.get(cls.ADMIN_PLAYERS_FILTER_CLUBS_SEARCH_KEY, '')

    ADMIN_PLAYERS_FILTER_GENDERS_KEY: str = 'admin_players_filter_genders'

    @classmethod
    def set_session_admin_players_filter_genders(
        cls, request: HTMXRequest, genders: list[PlayerGender]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_GENDERS_KEY] = genders

    @classmethod
    def get_session_admin_players_filter_genders(
        cls, request: HTMXRequest
    ) -> list[PlayerGender]:
        # type-casting is needed because the value returned by Session.get is serialized
        # when stored from a previous request (and kept as-is if stored by the current request)
        return [
            d if isinstance(d, PlayerGender) else PlayerGender(d)
            for d in request.session.get(cls.ADMIN_PLAYERS_FILTER_GENDERS_KEY, [])
        ]

    ADMIN_PLAYERS_FILTER_CHECK_INS_KEY: str = 'admin_players_filter_check_ins'

    @classmethod
    def set_session_admin_players_filter_check_ins(
        cls, request: HTMXRequest, check_ins: list[bool | None]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_CHECK_INS_KEY] = check_ins

    @classmethod
    def get_session_admin_players_filter_check_ins(
        cls, request: HTMXRequest
    ) -> list[bool | None]:
        return request.session.get(cls.ADMIN_PLAYERS_FILTER_CHECK_INS_KEY, [])

    ADMIN_PLAYERS_FILTER_TOURNAMENTS_KEY: str = 'admin_players_filter_tournaments'

    @classmethod
    def set_session_admin_players_filter_tournaments(
        cls, request: HTMXRequest, tournament_ids: list[int]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_TOURNAMENTS_KEY] = tournament_ids

    @classmethod
    def get_session_admin_players_filter_tournaments(
        cls, request: HTMXRequest
    ) -> list[int]:
        return request.session.get(cls.ADMIN_PLAYERS_FILTER_TOURNAMENTS_KEY, [])

    ADMIN_PLAYERS_FILTER_CATEGORIES_KEY: str = 'admin_players_filter_categories'

    @classmethod
    def set_session_admin_players_filter_categories(
        cls, request: HTMXRequest, categories: list[PlayerCategory]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_CATEGORIES_KEY] = categories

    @classmethod
    def get_session_admin_players_filter_categories(
        cls, request: HTMXRequest
    ) -> list[PlayerCategory]:
        # type-casting is needed because the value returned by Session.get is serialized
        # when stored from a previous request (and kept as-is if stored by the current request)
        return [
            d if isinstance(d, PlayerCategory) else PlayerCategory(d)
            for d in request.session.get(cls.ADMIN_PLAYERS_FILTER_CATEGORIES_KEY, [])
        ]

    ADMIN_PLAYERS_FILTER_NAME_KEY: str = 'admin_players_filter_name'

    @classmethod
    def set_session_admin_players_filter_name(cls, request: HTMXRequest, name: str):
        request.session[cls.ADMIN_PLAYERS_FILTER_NAME_KEY] = name

    @classmethod
    def get_session_admin_players_filter_name(cls, request: HTMXRequest) -> str:
        return request.session.get(cls.ADMIN_PLAYERS_FILTER_NAME_KEY, '')
