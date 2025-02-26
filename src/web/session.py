import logging
import time

from litestar.contrib.htmx.request import HTMXRequest

from common import get_logger
from common.papi_web_config import PapiWebConfig
from data.event import Event
from data.player import FederationTuple, LeagueTuple, ClubTuple
from data.util import PlayerGender, PlayerFFELicence, PlayerCategory

logger: logging.Logger = get_logger()


class SessionHandler:
    AUTH_SESSION_KEY: str = 'auth'

    @classmethod
    def store_password(cls, request: HTMXRequest, event: Event, password: str | None):
        if cls.AUTH_SESSION_KEY not in request.session:
            request.session[cls.AUTH_SESSION_KEY]: dict[str, str] = {}
        request.session[cls.AUTH_SESSION_KEY][event.uniq_id] = password

    @classmethod
    def get_stored_password(cls, request: HTMXRequest, event: Event) -> str | None:
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
        request.session[cls.LAST_RESULT_UPDATED_SESSION_KEY]: dict[
            str, int | str | float
        ] = {
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
        request.session[cls.USER_LAST_ILLEGAL_MOVE_UPDATED_KEY]: dict[
            str, int | str | float
        ] = {
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
        request.session[cls.USER_LAST_CHECK_IN_UPDATED_KEY]: dict[
            str, int | str | float
        ] = {
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
        request.session[cls.ADMIN_SCREENS_SHOW_FAMILY_SCREENS_KEY]: bool = b

    @classmethod
    def get_session_admin_screens_show_family_screens(
        cls, request: HTMXRequest
    ) -> bool:
        return request.session.get(cls.ADMIN_SCREENS_SHOW_FAMILY_SCREENS_KEY, False)

    ADMIN_SCREENS_SHOW_DETAILS_KEY: str = 'admin_screens_show_details'

    @classmethod
    def set_session_admin_screens_show_details(cls, request: HTMXRequest, b: bool):
        request.session[cls.ADMIN_SCREENS_SHOW_DETAILS_KEY]: bool = b

    @classmethod
    def get_session_admin_screens_show_details(cls, request: HTMXRequest) -> bool:
        return request.session.get(cls.ADMIN_SCREENS_SHOW_DETAILS_KEY, False)

    ADMIN_FAMILIES_SHOW_DETAILS_KEY: str = 'admin_families_show_details'

    @classmethod
    def set_session_admin_families_show_details(cls, request: HTMXRequest, b: bool):
        request.session[cls.ADMIN_FAMILIES_SHOW_DETAILS_KEY]: bool = b

    @classmethod
    def get_session_admin_families_show_details(cls, request: HTMXRequest) -> bool:
        return request.session.get(cls.ADMIN_FAMILIES_SHOW_DETAILS_KEY, False)

    ADMIN_ROTATORS_SHOW_DETAILS_KEY: str = 'admin_rotators_show_details'

    @classmethod
    def set_session_admin_rotators_show_details(cls, request: HTMXRequest, b: bool):
        request.session[cls.ADMIN_ROTATORS_SHOW_DETAILS_KEY]: bool = b

    @classmethod
    def get_session_admin_rotators_show_details(cls, request: HTMXRequest) -> bool:
        return request.session.get(cls.ADMIN_ROTATORS_SHOW_DETAILS_KEY, False)

    ADMIN_SCREENS_SCREEN_TYPES_KEY: str = 'admin_screens_screen_types'

    @classmethod
    def set_session_admin_screens_screen_types(
        cls, request: HTMXRequest, screen_types: list[str]
    ):
        request.session[cls.ADMIN_SCREENS_SCREEN_TYPES_KEY]: list[str] = screen_types

    @classmethod
    def get_session_admin_screens_screen_types(cls, request: HTMXRequest) -> list[str]:
        return request.session.get(
            cls.ADMIN_SCREENS_SCREEN_TYPES_KEY,
            ['boards', 'input', 'players', 'results', 'image'],
        )

    LOCALE_KEY: str = 'locale'

    @classmethod
    def set_session_locale(cls, request: HTMXRequest, locale: str):
        request.session[cls.LOCALE_KEY]: str = locale

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
            'origin',
            'tournament',
        ]
        request.session[cls.ADMIN_PLAYERS_SORT_KEY]: str = players_sort

    @classmethod
    def get_session_admin_players_sort(cls, request: HTMXRequest) -> str:
        return request.session.get(cls.ADMIN_PLAYERS_SORT_KEY, 'alpha')

    ADMIN_PLAYERS_FILTER_COLUMNS_KEY: str = 'admin_players_filter_columns'

    @classmethod
    def set_session_admin_players_filter_columns(
        cls, request: HTMXRequest, columns: list[str]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_COLUMNS_KEY]: list[str] = columns

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
        cls, request: HTMXRequest, federation_tuples: list[FederationTuple]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_FEDERATIONS_KEY]: list[
            FederationTuple
        ] = federation_tuples

    @classmethod
    def get_session_admin_players_filter_federations(
        cls, request: HTMXRequest
    ) -> list[FederationTuple]:
        # type-casting is needed because the value returned by Session.get is serialized
        # when stored from a previous request (and kept as-is if stored by the current request)
        return [
            d if isinstance(d, FederationTuple) else FederationTuple(d['federation'])
            for d in request.session.get(cls.ADMIN_PLAYERS_FILTER_FEDERATIONS_KEY, [])
        ]

    ADMIN_PLAYERS_FILTER_LEAGUES_KEY: str = 'admin_players_filter_leagues'

    @classmethod
    def set_session_admin_players_filter_leagues(
        cls, request: HTMXRequest, league_tuples: list[LeagueTuple]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_LEAGUES_KEY]: list[LeagueTuple] = (
            league_tuples
        )

    @classmethod
    def get_session_admin_players_filter_leagues(
        cls, request: HTMXRequest
    ) -> list[LeagueTuple]:
        # type-casting is needed because the value returned by Session.get is serialized
        # when stored from a previous request (and kept as-is if stored by the current request)
        return [
            d
            if isinstance(d, LeagueTuple)
            else LeagueTuple(d['federation'], d['league'])
            for d in request.session.get(cls.ADMIN_PLAYERS_FILTER_LEAGUES_KEY, [])
        ]

    ADMIN_PLAYERS_FILTER_CLUBS_KEY: str = 'admin_players_filter_clubs'

    @classmethod
    def set_session_admin_players_filter_clubs(
        cls, request: HTMXRequest, club_tuples: list[ClubTuple]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_CLUBS_KEY]: list[ClubTuple] = (
            club_tuples
        )

    @classmethod
    def get_session_admin_players_filter_clubs(
        cls, request: HTMXRequest
    ) -> list[ClubTuple]:
        # type-casting is needed because the value returned by Session.get is serialized
        # when stored from a previous request (and kept as-is if stored by the current request)
        return [
            d
            if isinstance(d, ClubTuple)
            else ClubTuple(d['federation'], d['league'], d['club'])
            for d in request.session.get(cls.ADMIN_PLAYERS_FILTER_CLUBS_KEY, [])
        ]

    ADMIN_PLAYERS_FILTER_GENDERS_KEY: str = 'admin_players_filter_genders'

    @classmethod
    def set_session_admin_players_filter_genders(
        cls, request: HTMXRequest, genders: list[PlayerGender]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_GENDERS_KEY]: list[PlayerGender] = (
            genders
        )

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

    ADMIN_PLAYERS_FILTER_LICENCES_KEY: str = 'admin_players_filter_licences'

    @classmethod
    def set_session_admin_players_filter_licences(
        cls, request: HTMXRequest, licences: list[PlayerFFELicence]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_LICENCES_KEY]: list[
            PlayerFFELicence
        ] = licences

    @classmethod
    def get_session_admin_players_filter_licences(
        cls, request: HTMXRequest
    ) -> list[PlayerFFELicence]:
        # type-casting is needed because the value returned by Session.get is serialized
        # when stored from a previous request (and kept as-is if stored by the current request)
        return [
            d if isinstance(d, PlayerFFELicence) else PlayerFFELicence(d)
            for d in request.session.get(cls.ADMIN_PLAYERS_FILTER_LICENCES_KEY, [])
        ]

    ADMIN_PLAYERS_FILTER_CHECK_INS_KEY: str = 'admin_players_filter_check_ins'

    @classmethod
    def set_session_admin_players_filter_check_ins(
        cls, request: HTMXRequest, check_ins: list[bool | None]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_CHECK_INS_KEY]: list[bool] = check_ins

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
        request.session[cls.ADMIN_PLAYERS_FILTER_TOURNAMENTS_KEY]: list[int] = (
            tournament_ids
        )

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
        request.session[cls.ADMIN_PLAYERS_FILTER_CATEGORIES_KEY]: list[
            PlayerCategory
        ] = categories

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
        request.session[cls.ADMIN_PLAYERS_FILTER_NAME_KEY]: str = name

    @classmethod
    def get_session_admin_players_filter_name(cls, request: HTMXRequest) -> str:
        return request.session.get(cls.ADMIN_PLAYERS_FILTER_NAME_KEY, '')

    ADMIN_PLAYERS_FILTER_ORIGIN_KEY: str = 'admin_players_filter_origin'

    @classmethod
    def set_session_admin_players_filter_origin(cls, request: HTMXRequest, origin: str):
        request.session[cls.ADMIN_PLAYERS_FILTER_ORIGIN_KEY]: str = origin

    @classmethod
    def get_session_admin_players_filter_origin(cls, request: HTMXRequest) -> str:
        return request.session.get(cls.ADMIN_PLAYERS_FILTER_ORIGIN_KEY, '')
