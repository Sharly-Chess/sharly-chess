import time
from contextlib import suppress
from logging import Logger
from typing import TYPE_CHECKING

from litestar.plugins.htmx import HTMXRequest

from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.account import Account
from data.input_output import DataSourceManager
from data.player import Federation, Club
from data.safety_mode import SafetyMode
from utils.enum import PlayerGender, PlayerCategory

if TYPE_CHECKING:
    from data.event import Event
    from web.controllers.admin.pairings_admin_controller import PageIdentifier

logger: Logger = get_logger()


class SessionHandler:
    USER_ACCOUNT_SESSION_KEY: str = 'user_account'
    USER_ACCOUNT_PASSWORD_HASH_SESSION_KEY: str = 'user_account_password_hash'

    @classmethod
    def store_user_account(
        cls,
        request: HTMXRequest,
        event: 'Event',
        user_account: Account | None,
    ):
        if cls.USER_ACCOUNT_SESSION_KEY not in request.session:
            request.session[cls.USER_ACCOUNT_SESSION_KEY] = {}
        if cls.USER_ACCOUNT_PASSWORD_HASH_SESSION_KEY not in request.session:
            request.session[cls.USER_ACCOUNT_PASSWORD_HASH_SESSION_KEY] = {}
        if user_account:
            request.session[cls.USER_ACCOUNT_SESSION_KEY][event.uniq_id] = (
                user_account.id
            )
            # store the password hash at the time the authentication is successful
            # to be able to invalidate the session if the password is changed
            request.session[cls.USER_ACCOUNT_PASSWORD_HASH_SESSION_KEY][
                event.uniq_id
            ] = user_account.password_hash
        else:
            with suppress(KeyError):
                del request.session[cls.USER_ACCOUNT_SESSION_KEY][event.uniq_id]
                del request.session[cls.USER_ACCOUNT_PASSWORD_HASH_SESSION_KEY][
                    event.uniq_id
                ]

    @classmethod
    def get_user_account(
        cls,
        request: HTMXRequest,
        event: 'Event',
    ) -> Account:
        try:
            account: Account = event.active_user_accounts_by_id[
                request.session[cls.USER_ACCOUNT_SESSION_KEY][event.uniq_id]
            ]
        except KeyError:
            return event.anonymous_account
        # if the password has been changed, disconnect the client to force the re-authentication
        if (
            account.password_hash
            != request.session[cls.USER_ACCOUNT_PASSWORD_HASH_SESSION_KEY][
                event.uniq_id
            ]
        ):
            logger.info(
                'Password has changed for account [%s], force the re-authentication.',
                account.full_name,
            )
            cls.store_user_account(request, event, None)
            return event.anonymous_account
        return account

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

    ADMIN_ACCOUNTS_SHOW_DETAILS_KEY: str = 'admin_accounts_show_details'

    @classmethod
    def set_session_admin_accounts_show_details(cls, request: HTMXRequest, b: bool):
        request.session[cls.ADMIN_ACCOUNTS_SHOW_DETAILS_KEY] = b

    @classmethod
    def get_session_admin_accounts_show_details(cls, request: HTMXRequest) -> bool:
        return request.session.get(cls.ADMIN_ACCOUNTS_SHOW_DETAILS_KEY, False)

    ADMIN_TOURNAMENT_CRITERION_ADD_OTHER_ACTIVE_KEY: str = (
        'admin_tournament_criterion_add_other_active'
    )

    @classmethod
    def set_session_admin_tournament_criterion_add_other_active(
        cls, request: HTMXRequest, b: bool
    ):
        request.session[cls.ADMIN_TOURNAMENT_CRITERION_ADD_OTHER_ACTIVE_KEY] = b

    @classmethod
    def get_session_admin_tournament_criterion_add_other_active(
        cls, request: HTMXRequest
    ) -> bool:
        return request.session.get(
            cls.ADMIN_TOURNAMENT_CRITERION_ADD_OTHER_ACTIVE_KEY, False
        )

    ADMIN_TIE_BREAK_ADD_OTHER_ACTIVE_KEY = 'admin_tie_break_add_other_active'

    @classmethod
    def set_session_admin_tie_break_add_other_active(
        cls, request: HTMXRequest, b: bool
    ):
        request.session[cls.ADMIN_TIE_BREAK_ADD_OTHER_ACTIVE_KEY] = b

    @classmethod
    def get_session_admin_tie_break_add_other_active(cls, request: HTMXRequest) -> bool:
        return request.session.get(cls.ADMIN_TIE_BREAK_ADD_OTHER_ACTIVE_KEY, False)

    ADMIN_EVENTS_SHOW_DETAILS_KEY: str = 'admin_events_show_details'

    @classmethod
    def set_session_admin_events_show_details(cls, request: HTMXRequest, b: bool):
        request.session[cls.ADMIN_EVENTS_SHOW_DETAILS_KEY] = b

    @classmethod
    def get_session_admin_events_show_details(cls, request: HTMXRequest) -> bool:
        return request.session.get(cls.ADMIN_EVENTS_SHOW_DETAILS_KEY, False)

    ADMIN_PAIRINGS_SHOW_WITHOUT_RESULTS_KEY: str = 'admin_pairings_show_without_results'

    @classmethod
    def set_session_admin_pairings_show_without_results(
        cls, request: HTMXRequest, b: bool
    ):
        request.session[cls.ADMIN_PAIRINGS_SHOW_WITHOUT_RESULTS_KEY] = b

    @classmethod
    def get_session_admin_pairings_show_without_results(
        cls, request: HTMXRequest
    ) -> bool:
        return request.session.get(cls.ADMIN_PAIRINGS_SHOW_WITHOUT_RESULTS_KEY, False)

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
                [],
            )
        )

    LOCALE_KEY: str = 'locale'

    @classmethod
    def set_session_locale(cls, request: HTMXRequest, locale: str):
        request.session[cls.LOCALE_KEY] = locale

    @classmethod
    def get_session_locale(cls, request: HTMXRequest) -> str:
        return request.session.get(cls.LOCALE_KEY, SharlyChessConfig().locale)

    ADMIN_PLAYERS_EVENT_KEY: str = 'admin_players_event'

    @classmethod
    def set_session_admin_players_event(cls, request: HTMXRequest, event_uniq_id: str):
        request.session[cls.ADMIN_PLAYERS_EVENT_KEY] = event_uniq_id

    @classmethod
    def get_session_admin_player_event(cls, request: HTMXRequest) -> str | None:
        return request.session.get(cls.ADMIN_PLAYERS_EVENT_KEY, None)

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
            SharlyChessConfig.default_players_filter_columns,
        )

    ADMIN_PLAYERS_FILTER_FEDERATIONS_KEY: str = 'admin_players_filter_federations'

    @classmethod
    def set_session_admin_players_filter_federations(
        cls, request: HTMXRequest, federations: list[Federation]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_FEDERATIONS_KEY] = [
            federation.name for federation in federations
        ]

    @classmethod
    def get_session_admin_players_filter_federations(
        cls, request: HTMXRequest
    ) -> list[Federation]:
        return [
            Federation(federation_name)
            for federation_name in request.session.get(
                cls.ADMIN_PLAYERS_FILTER_FEDERATIONS_KEY, []
            )
        ]

    ADMIN_PLAYERS_FILTER_CLUBS_KEY: str = 'admin_players_filter_clubs'

    @classmethod
    def set_session_admin_players_filter_clubs(
        cls, request: HTMXRequest, clubs: list[Club]
    ):
        request.session[cls.ADMIN_PLAYERS_FILTER_CLUBS_KEY] = [
            club.name for club in clubs
        ]

    @classmethod
    def get_session_admin_players_filter_clubs(cls, request: HTMXRequest) -> list[Club]:
        return [
            Club(club_name)
            for club_name in request.session.get(cls.ADMIN_PLAYERS_FILTER_CLUBS_KEY, [])
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
        request.session[cls.ADMIN_PLAYERS_FILTER_GENDERS_KEY] = [
            gender.value for gender in genders
        ]

    @classmethod
    def get_session_admin_players_filter_genders(
        cls, request: HTMXRequest
    ) -> list[PlayerGender]:
        return [
            PlayerGender(gender_value)
            for gender_value in request.session.get(
                cls.ADMIN_PLAYERS_FILTER_GENDERS_KEY, []
            )
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
        request.session[cls.ADMIN_PLAYERS_FILTER_CATEGORIES_KEY] = [
            category.value for category in categories
        ]

    @classmethod
    def get_session_admin_players_filter_categories(
        cls, request: HTMXRequest
    ) -> list[PlayerCategory]:
        return [
            PlayerCategory(category_value)
            for category_value in request.session.get(
                cls.ADMIN_PLAYERS_FILTER_CATEGORIES_KEY, []
            )
        ]

    ADMIN_PLAYERS_FILTER_NAME_KEY: str = 'admin_players_filter_name'

    @classmethod
    def set_session_admin_players_filter_name(cls, request: HTMXRequest, name: str):
        request.session[cls.ADMIN_PLAYERS_FILTER_NAME_KEY] = name

    @classmethod
    def get_session_admin_players_filter_name(cls, request: HTMXRequest) -> str:
        return request.session.get(cls.ADMIN_PLAYERS_FILTER_NAME_KEY, '')

    ADMIN_PLAYERS_SEARCH_RESULTS_ID_KEY = 'admin_players_search_results_id'

    @classmethod
    def set_session_admin_players_search_results_id(
        cls, request: HTMXRequest, search_results_id: int
    ):
        request.session[cls.ADMIN_PLAYERS_SEARCH_RESULTS_ID_KEY] = search_results_id

    @classmethod
    def get_session_admin_players_search_results_id(
        cls, request: HTMXRequest
    ) -> int | None:
        return request.session.get(cls.ADMIN_PLAYERS_SEARCH_RESULTS_ID_KEY, None)

    ADMIN_PLAYERS_ACTIVE_DATA_SOURCE_KEY: str = 'admin_players_active_data_source'

    @classmethod
    def set_session_admin_players_active_data_source(
        cls, request: HTMXRequest, data_source_id: str
    ):
        request.session[cls.ADMIN_PLAYERS_ACTIVE_DATA_SOURCE_KEY] = data_source_id

    @classmethod
    def get_session_admin_players_active_data_source(cls, request: HTMXRequest) -> str:
        return request.session.get(
            cls.ADMIN_PLAYERS_ACTIVE_DATA_SOURCE_KEY,
            DataSourceManager().entity_types()[0].static_id(),
        )

    ADMIN_PAIRINGS_SAFETY_MODE_KEY = 'admin_pairings_safety_mode'

    @classmethod
    def set_session_admin_pairings_safety_mode(
        cls, request: HTMXRequest, safety_mode: SafetyMode
    ):
        request.session[cls.ADMIN_PAIRINGS_SAFETY_MODE_KEY] = safety_mode.value

    @classmethod
    def get_session_admin_pairings_safety_mode(cls, request: HTMXRequest) -> SafetyMode:
        return SafetyMode(
            request.session.get(cls.ADMIN_PAIRINGS_SAFETY_MODE_KEY, SafetyMode.SAFE)
        )

    ADMIN_PAIRINGS_PAGE_IDENTIFIER_KEY = 'admin_pairings_page_identifier'

    @classmethod
    def set_session_admin_pairings_page_identifier(
        cls, request: HTMXRequest, page_identifier: 'PageIdentifier'
    ):
        request.session[cls.ADMIN_PAIRINGS_PAGE_IDENTIFIER_KEY] = (
            page_identifier.to_json()
        )

    @classmethod
    def get_session_admin_pairings_page_identifier(
        cls, request: HTMXRequest
    ) -> 'PageIdentifier | None':
        from web.controllers.admin.pairings_admin_controller import PageIdentifier

        if page_identifier := request.session.get(
            cls.ADMIN_PAIRINGS_PAGE_IDENTIFIER_KEY, None
        ):
            return PageIdentifier.from_json(page_identifier)
        return None

    ADMIN_PLAYER_ADD_OTHER_ACTIVE_KEY: str = 'admin_player_add_other_active'

    @classmethod
    def set_session_admin_player_add_other_active(cls, request: HTMXRequest, b: bool):
        request.session[cls.ADMIN_PLAYER_ADD_OTHER_ACTIVE_KEY] = b

    @classmethod
    def get_session_admin_player_add_other_active(cls, request: HTMXRequest) -> bool:
        return request.session.get(cls.ADMIN_PLAYER_ADD_OTHER_ACTIVE_KEY, False)

    ADMIN_PRIZE_ADD_OTHER_ACTIVE_KEY: str = 'admin_prize_add_other_active'

    @classmethod
    def set_session_admin_prize_add_other_active(cls, request: HTMXRequest, b: bool):
        request.session[cls.ADMIN_PRIZE_ADD_OTHER_ACTIVE_KEY] = b

    @classmethod
    def get_session_admin_prize_add_other_active(cls, request: HTMXRequest) -> bool:
        return request.session.get(cls.ADMIN_PRIZE_ADD_OTHER_ACTIVE_KEY, False)

    ADMIN_PRIZE_CATEGORY_ADD_OTHER_ACTIVE_KEY: str = (
        'admin_prize_category_add_other_active'
    )

    @classmethod
    def set_session_admin_prize_category_add_other_active(
        cls, request: HTMXRequest, b: bool
    ):
        request.session[cls.ADMIN_PRIZE_CATEGORY_ADD_OTHER_ACTIVE_KEY] = b

    @classmethod
    def get_session_admin_prize_category_add_other_active(
        cls, request: HTMXRequest
    ) -> bool:
        return request.session.get(cls.ADMIN_PRIZE_CATEGORY_ADD_OTHER_ACTIVE_KEY, False)

    ADMIN_PRIZE_CRITERION_ADD_OTHER_ACTIVE_KEY: str = (
        'admin_prize_criterion_add_other_active'
    )

    @classmethod
    def set_session_admin_prize_criterion_add_other_active(
        cls, request: HTMXRequest, b: bool
    ):
        request.session[cls.ADMIN_PRIZE_CRITERION_ADD_OTHER_ACTIVE_KEY] = b

    @classmethod
    def get_session_admin_prize_criterion_add_other_active(
        cls, request: HTMXRequest
    ) -> bool:
        return request.session.get(
            cls.ADMIN_PRIZE_CRITERION_ADD_OTHER_ACTIVE_KEY, False
        )

    ADMIN_PRIZES_SHOW_DETAILS_KEY: str = 'admin_prizes_show_details'

    @classmethod
    def set_session_admin_prizes_show_details(cls, request: HTMXRequest, b: bool):
        request.session[cls.ADMIN_PRIZES_SHOW_DETAILS_KEY] = b

    @classmethod
    def get_session_admin_prizes_show_details(cls, request: HTMXRequest) -> bool:
        return request.session.get(cls.ADMIN_PRIZES_SHOW_DETAILS_KEY, False)

    PRINT_TOURNAMENT_KEY: str = 'admin_print_last_tournament'

    @classmethod
    def set_session_admin_print_last_tournaments(
        cls, request: HTMXRequest, event_uniq_id: str, tournament_ids: list[int]
    ):
        request.session[cls.PRINT_TOURNAMENT_KEY] = (event_uniq_id, tournament_ids)

    @classmethod
    def get_session_admin_print_last_tournaments(
        cls, request: HTMXRequest
    ) -> tuple[str, list[int]] | None:
        return request.session.get(cls.PRINT_TOURNAMENT_KEY, None)

    PAIRINGS_SELECTED_TOURNAMENT_KEY: str = 'admin_pairings_selected_tournament'

    @classmethod
    def set_session_admin_pairings_selected_tournament(
        cls, request: HTMXRequest, event_uniq_id: str, tournament_id: int
    ):
        if cls.PAIRINGS_SELECTED_TOURNAMENT_KEY not in request.session:
            request.session[cls.PAIRINGS_SELECTED_TOURNAMENT_KEY] = {}
        request.session[cls.PAIRINGS_SELECTED_TOURNAMENT_KEY][event_uniq_id] = (
            tournament_id
        )

    @classmethod
    def get_session_admin_pairings_selected_tournament(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> int | None:
        try:
            return request.session[cls.PAIRINGS_SELECTED_TOURNAMENT_KEY][event_uniq_id]
        except KeyError:
            return None

    PAIRINGS_SELECTED_ROUND_KEY: str = 'admin_pairings_selected_round'

    @classmethod
    def set_session_admin_pairings_selected_round(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
        round: int,
    ):
        # dict keys are stored as strings because they are always read as strings
        if cls.PAIRINGS_SELECTED_ROUND_KEY not in request.session:
            request.session[cls.PAIRINGS_SELECTED_ROUND_KEY] = {}
        if event_uniq_id not in request.session[cls.PAIRINGS_SELECTED_ROUND_KEY]:
            request.session[cls.PAIRINGS_SELECTED_ROUND_KEY][event_uniq_id] = {}
        request.session[cls.PAIRINGS_SELECTED_ROUND_KEY][event_uniq_id][
            str(tournament_id)
        ] = round

    @classmethod
    def get_session_admin_pairings_selected_round(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int,
    ) -> int | None:
        # dict keys are stored as strings because they are always read as strings
        try:
            return request.session[cls.PAIRINGS_SELECTED_ROUND_KEY][event_uniq_id][
                str(tournament_id)
            ]
        except KeyError:
            return None
