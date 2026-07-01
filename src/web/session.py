from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, is_dataclass
from logging import Logger
from typing import Any, ClassVar, cast, get_args, get_origin

from litestar.plugins.htmx import HTMXRequest

from common.i18n import locales, DEFAULT_LOCALE
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.event import Event
from data.input_output.dict_reader import dict_to_dataclass
from data.safety_mode import SafetyMode
from data.tournament import Tournament

logger: Logger = get_logger()


class SessionVariable[T](ABC):
    def __init__(self, request: HTMXRequest):
        self.request = request

    @property
    @abstractmethod
    def key(self) -> str:
        """Key used to store and retrieve the variable from the session.
        Has to be unique amongst all session variables."""

    @property
    @abstractmethod
    def default_value(self) -> T:
        """Default value used for the variable when nothing's stored in the session."""

    def get(self) -> T:
        return self.request.session.get(self.key, self.default_value)

    def set(self, value: T):
        self.request.session[self.key] = value

    def unset(self):
        self.request.session.pop(self.key, None)


class NoneSessionVariable[T](SessionVariable[T | None], ABC):
    @property
    def default_value(self) -> T | None:
        return None


class BoolSessionVariable(SessionVariable[bool], ABC):
    @property
    def default_value(self) -> bool:
        return False


class StrSessionVariable(SessionVariable[str], ABC):
    @property
    def default_value(self) -> str:
        return ''


class ListSessionVariable[T](SessionVariable[list[T]], ABC):
    @property
    def default_value(self) -> list[T]:
        return []


class WrapperListSessionVariable[T](ListSessionVariable[T], ABC):
    @abstractmethod
    def from_session_value(self, value: Any) -> T:
        """Initialize an object of type T from the session value."""

    @abstractmethod
    def to_session_value(self, element: T) -> Any:
        """Get the value stored in the session for an element."""

    def get(self) -> list[T]:
        return [
            self.from_session_value(value)
            for value in self.request.session.get(self.key, self.default_value)
        ]

    def set(self, value: list[T]):
        self.request.session[self.key] = [
            self.to_session_value(element) for element in value
        ]


class SubKeySessionVariable[T](SessionVariable[T], ABC):
    def __init__(self, request: HTMXRequest, sub_key: str):
        super().__init__(request)
        self.sub_key = sub_key

    def set(self, value: T):
        if self.key not in self.request.session:
            self.request.session[self.key] = {}
        self.request.session[self.key][self.sub_key] = value

    def get(self) -> T:
        if self.key not in self.request.session:
            return self.default_value
        return self.request.session[self.key].get(self.sub_key, self.default_value)

    def unset(self):
        if self.key not in self.request.session:
            return
        self.request.session[self.key].pop(self.sub_key, None)


class EventSessionVariable[T](SubKeySessionVariable[T], ABC):
    def __init__(self, request: HTMXRequest, event: Event):
        super().__init__(request, event.uniq_id)


class EventNoneSessionVariable[T](EventSessionVariable[T | None], ABC):
    @property
    def default_value(self) -> T | None:
        return None


class TournamentSessionVariable[T](SubKeySessionVariable[T], ABC):
    def __init__(self, request: HTMXRequest, tournament: Tournament):
        super().__init__(request, f'{tournament.event.uniq_id}|{tournament.id}')


class DataclassSessionVariable[T](SessionVariable[T], ABC):
    _data_class: ClassVar[type[Any]]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        for base in getattr(cls, '__orig_bases__', ()):
            if get_origin(base) is DataclassSessionVariable:
                (dc,) = get_args(base)

                if not isinstance(dc, type):
                    raise TypeError(
                        f'{cls.__name__} must be parametrized with a dataclass *type*, '
                        f'got {dc!r}'
                    )

                if not is_dataclass(dc):
                    raise TypeError(
                        f'{cls.__name__} must be parametrized with a dataclass type, '
                        f'got {dc.__name__}'
                    )

                cls._data_class = dc
                return

        raise TypeError(
            f'{cls.__name__} must inherit as DataclassSessionVariable[SomeDataclass]'
        )

    @property
    def data_class(self) -> type[T]:
        return self.__class__._data_class

    @property
    def default_value(self) -> T:
        return self.data_class()

    def get(self) -> T:
        if self.key not in self.request.session:
            return self.default_value
        return dict_to_dataclass(self.data_class, self.request.session[self.key])

    def set(self, value: T):
        self.request.session[self.key] = asdict(cast(Any, value))


class SessionUserAccountId(EventNoneSessionVariable[int]):
    @property
    def key(self) -> str:
        return 'account_id'


class SessionUserAccountPasswordHash(EventNoneSessionVariable[str]):
    @property
    def key(self) -> str:
        return 'account_password_hash'


@dataclass
class LastBoardUpdated:
    tournament_id: int = 0
    round: int = 0
    board_id: int = 0
    expiration: float = 0.0


class SessionLastResultUpdated(DataclassSessionVariable[LastBoardUpdated]):
    @property
    def key(self) -> str:
        return 'last_result_updated'


@dataclass
class LastPlayerUpdated:
    tournament_id: int = 0
    player_id: int = 0
    expiration: float = 0.0


class SessionLastIllegalMoveUpdated(DataclassSessionVariable[LastPlayerUpdated]):
    @property
    def key(self) -> str:
        return 'last_illegal_move_updated'


class SessionLastCheckInUpdated(DataclassSessionVariable[LastPlayerUpdated]):
    @property
    def key(self) -> str:
        return 'last_check_in_updated'


class SessionScreensShowFamilyScreens(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'screens_show_family_screens'


class SessionScreensShowDetails(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'screens_show_details'


class SessionFamiliesShowDetails(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'families_show_details'


class SessionRotatorsShowDetails(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'rotators_show_details'


class SessionMenusShowDetails(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'menus_show_details'


class SessionAccountsShowDetails(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'accounts_show_details'


class SessionPrizesShowDetails(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'prizes_show_details'


class SessionTournamentsShowDetails(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'tournaments_show_details'


class SessionEventsShowDetails(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'events_show_details'


class SessionTeamsShowRoster(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'teams_show_roster'

    @property
    def default_value(self) -> bool:
        return True


class SessionTeamsShowLineup(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'teams_show_lineup'

    @property
    def default_value(self) -> bool:
        return True


class SessionTimersAddOtherActive(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'timers_add_other_active'


class SessionTournamentCriteriaAddOtherActive(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'tournament_criteria_add_other_active'


class SessionTieBreakAddOtherActive(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'tie_break_add_other_active'


class SessionPairingsShowWithoutResults(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'pairings_show_without_results'


class SessionScreensScreenTypes(SessionVariable[set[str]]):
    @property
    def key(self) -> str:
        return 'screens_screen_types'

    @property
    def default_value(self) -> set[str]:
        return set()

    def get(self) -> set[str]:
        return set(super().get())

    def set(self, value: set[str]):
        self.request.session[self.key] = list(value)


class SessionLocale(SessionVariable[str]):
    @property
    def key(self) -> str:
        return 'locale'

    @property
    def default_value(self) -> str:
        return SharlyChessConfig().locale

    def get(self) -> str:
        locale = super().get()
        if locale not in locales:
            locale = DEFAULT_LOCALE
            self.set(locale)
        return locale


class SessionPlayersSearch(EventNoneSessionVariable[str]):
    @property
    def key(self) -> str:
        return 'players_table_search'


class SessionPlayersHiddenColumns(EventNoneSessionVariable[list[str]]):
    @property
    def key(self) -> str:
        return 'players_hidden_columns'


class SessionPlayersDisabledColumns(EventSessionVariable[list[str]]):
    @property
    def key(self) -> str:
        return 'players_disabled_columns'

    @property
    def default_value(self) -> list[str]:
        return []


class SessionPlayersSort(EventSessionVariable[tuple[str, bool]]):
    @property
    def key(self) -> str:
        return 'players_sorting'

    @property
    def default_value(self) -> tuple[str, bool]:
        return '', True


class SessionPlayersFilters(EventSessionVariable[dict[str, list[str]]]):
    @property
    def key(self) -> str:
        return 'players_filters'

    @property
    def default_value(self) -> dict[str, list[str]]:
        return {}

    def set_column_filters(self, column_id: str, filter_keys: list[str]):
        filters = self.get()
        if not filter_keys:
            if column_id in filters:
                del filters[column_id]
        else:
            filters[column_id] = filter_keys
        self.set(filters)


class SessionPlayersEvent(NoneSessionVariable[str]):
    @property
    def key(self) -> str:
        return 'players_event'


class SessionPlayersSearchResultsId(NoneSessionVariable[int]):
    @property
    def key(self) -> str:
        return 'players_search_results_id'


class SessionPlayersActiveDataSource(SessionVariable[str]):
    @property
    def key(self) -> str:
        return 'players_active_data_source'

    @property
    def default_value(self) -> str:
        from data.input_output import DataSourceManager

        return DataSourceManager().entity_types()[0].static_id()


class SessionPlayersAddOtherActive(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'players_add_other_active'


class SessionTeamsAddOtherActive(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'teams_add_other_active'


class SessionPlayersImportUseDataSource(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'players_import_use_data_source'


class SessionPairingsSafetyMode(SessionVariable[SafetyMode]):
    @property
    def key(self) -> str:
        return 'pairings_safety_mode'

    @property
    def default_value(self) -> SafetyMode:
        return SafetyMode.SAFE

    def get(self) -> SafetyMode:
        return SafetyMode(super().get())

    def set(self, safety_mode: SafetyMode):
        self.request.session[self.key] = safety_mode.value


@dataclass
class PairingsPageIdentifier:
    event_uniq_id: str = ''
    tournament_id: int = 0
    round: int = 0


class SessionPairingsPageIdentifier(DataclassSessionVariable[PairingsPageIdentifier]):
    @property
    def key(self) -> str:
        return 'pairings_page_identifier'


class SessionPairingsSelectedTournament(EventNoneSessionVariable[int]):
    @property
    def key(self) -> str:
        return 'pairings_selected_tournament'


class SessionPairingsSelectedRound(TournamentSessionVariable[int | None]):
    @property
    def key(self) -> str:
        return 'pairings_selected_round'

    @property
    def default_value(self) -> int | None:
        return None


class SessionPrizeCategoriesAddOtherActive(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'prize_categories_add_other_active'


class SessionPrizeCriteriaAddOtherActive(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'prize_criteria_add_other_active'


class SessionPrizesAddOtherActive(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'prizes_add_other_active'


class SessionPrintLastTournaments(EventSessionVariable[list[int]]):
    @property
    def key(self) -> str:
        return 'print_last_tournaments'

    @property
    def default_value(self) -> list[int]:
        return []


class SessionDistributeType(StrSessionVariable):
    @property
    def key(self) -> str:
        return 'distribute_type'

    @property
    def default_value(self) -> str:
        return 'rating'


class SessionDistributeUseBalanceGroups(BoolSessionVariable):
    @property
    def key(self) -> str:
        return 'distribute_use_balance_groups'


class SessionDistributeUnselectedTournaments(EventSessionVariable[list[int]]):
    @property
    def key(self) -> str:
        return 'distribute_unselected_tournaments'

    @property
    def default_value(self) -> list[int]:
        return []


class SessionDistributePlayerCountByTournamentId(EventSessionVariable[dict[str, str]]):
    @property
    def key(self) -> str:
        return 'distribute_player_count_by_tournament_id'

    @property
    def default_value(self) -> dict[str, str]:
        return {}


class SessionDistributeGroupsById(EventSessionVariable[dict[str, list[int]]]):
    @property
    def key(self) -> str:
        return 'distribute_groups_by_id'

    @property
    def default_value(self) -> dict[str, list[int]]:
        return {}
