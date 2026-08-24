from enum import StrEnum, auto
from typing import Self

from common.i18n import _


class AuthActionCategory(StrEnum):
    APPLICATION = auto()
    EVENTS = auto()
    ACCESS = auto()
    TOURNAMENTS = auto()
    PLAYERS = auto()
    CHECK_IN = auto()
    PAIRINGS = auto()
    RESULTS = auto()
    SCREENS = auto()
    PRIZES = auto()
    DOCUMENTS = auto()

    @classmethod
    def categories(cls) -> list[Self]:
        return list(cls(c) for c in cls)

    @property
    def name(self) -> str:
        return self.localized_name()

    def localized_name(self, locale: str | None = None) -> str:
        match self:
            case AuthActionCategory.APPLICATION:
                return _('Application', locale)
            case AuthActionCategory.EVENTS:
                return _('Events', locale)
            case AuthActionCategory.ACCESS:
                return _('Access control', locale)
            case AuthActionCategory.TOURNAMENTS:
                return _('Tournaments', locale)
            case AuthActionCategory.PLAYERS:
                return _('Players', locale)
            case AuthActionCategory.CHECK_IN:
                return _('Check-in', locale)
            case AuthActionCategory.PAIRINGS:
                return _('Pairings', locale)
            case AuthActionCategory.RESULTS:
                return _('Results', locale)
            case AuthActionCategory.SCREENS:
                return _('Screens', locale)
            case AuthActionCategory.PRIZES:
                return _('Prizes', locale)
            case AuthActionCategory.DOCUMENTS:
                return _('Documents', locale)
            case _:
                raise ValueError(f'auth={self}')


class AuthAction(StrEnum):
    # Application
    MANAGE_APPLICATION_SETTINGS = auto()
    MANAGE_SOURCE_DATABASES = auto()
    MANAGE_ARCHIVES = auto()

    # Events access
    VIEW_PRIVATE_EVENTS = auto()
    VIEW_PASSED_EVENTS = auto()
    VIEW_DETAILED_EVENT_CARDS = auto()
    CREATE_EVENTS = auto()
    MANAGE_EVENTS = auto()

    # Event
    RENAME_EVENT = auto()
    UPDATE_EVENT = auto()
    VIEW_EVENT_CONFIG = auto()

    # Access
    MANAGE_ACCOUNTS = auto()

    # Tournament
    VIEW_TOURNAMENTS_TAB = auto()
    ADD_TOURNAMENTS = auto()
    UPDATE_TOURNAMENTS = auto()
    DELETE_TOURNAMENTS = auto()
    PUBLISH_RESULTS = auto()
    PUBLISH_RULES = auto()
    DOWNLOAD_FEES = auto()

    # Players
    VIEW_PLAYERS_TAB = auto()
    ADD_PLAYERS = auto()
    UPDATE_PLAYERS = auto()
    UPDATE_PLAYERS_HISTORY = auto()
    DELETE_PLAYERS = auto()
    DISTRIBUTE_PLAYERS = auto()

    # Check-in
    OPEN_CLOSE_CHECK_IN = auto()
    CHECK_IN_PLAYERS = auto()

    # Pairings
    VIEW_PAIRINGS_TAB = auto()
    USE_PAIRING_ENGINE = auto()
    MANUALLY_PAIR_PLAYERS = auto()
    UNPAIR_ROUND = auto()
    UNPAIR_BOARD = auto()
    PERMUTE_BOARD = auto()
    SET_CURRENT_ROUND = auto()
    SET_ZPB = auto()
    SET_HPB = auto()
    SET_FPB = auto()

    # Results
    ENTER_RESULTS = auto()
    UPDATE_RESULTS = auto()
    SET_ILLEGAL_MOVES = auto()
    SET_SPECIAL_RESULTS = auto()

    # Screens
    MANAGE_SCREENS = auto()
    VIEW_PRIVATE_SCREENS = auto()
    VIEW_PUBLIC_SCREENS = auto()

    # Prizes
    VIEW_PRIZES_TAB = auto()
    MANAGE_PRIZES = auto()

    # Documents
    GENERATE_DOCUMENTS = auto()

    @classmethod
    def actions(cls) -> list[Self]:
        return list(cls(a) for a in cls)

    @property
    def category(self) -> AuthActionCategory:
        match self:
            case (
                AuthAction.MANAGE_APPLICATION_SETTINGS
                | AuthAction.MANAGE_SOURCE_DATABASES
                | AuthAction.MANAGE_ARCHIVES
            ):
                return AuthActionCategory.APPLICATION
            case (
                AuthAction.VIEW_PRIVATE_EVENTS
                | AuthAction.VIEW_PASSED_EVENTS
                | AuthAction.VIEW_DETAILED_EVENT_CARDS
                | AuthAction.CREATE_EVENTS
                | AuthAction.MANAGE_EVENTS
                | AuthAction.RENAME_EVENT
                | AuthAction.UPDATE_EVENT
                | AuthAction.VIEW_EVENT_CONFIG
            ):
                return AuthActionCategory.EVENTS
            case AuthAction.MANAGE_ACCOUNTS:
                return AuthActionCategory.ACCESS
            case (
                AuthAction.VIEW_TOURNAMENTS_TAB
                | AuthAction.ADD_TOURNAMENTS
                | AuthAction.UPDATE_TOURNAMENTS
                | AuthAction.DELETE_TOURNAMENTS
                | AuthAction.PUBLISH_RESULTS
                | AuthAction.PUBLISH_RULES
                | AuthAction.DOWNLOAD_FEES
            ):
                return AuthActionCategory.TOURNAMENTS
            case (
                AuthAction.VIEW_PLAYERS_TAB
                | AuthAction.ADD_PLAYERS
                | AuthAction.UPDATE_PLAYERS
                | AuthAction.UPDATE_PLAYERS_HISTORY
                | AuthAction.DELETE_PLAYERS
                | AuthAction.DISTRIBUTE_PLAYERS
            ):
                return AuthActionCategory.PLAYERS
            case AuthAction.CHECK_IN_PLAYERS | AuthAction.OPEN_CLOSE_CHECK_IN:
                return AuthActionCategory.CHECK_IN
            case (
                AuthAction.VIEW_PAIRINGS_TAB
                | AuthAction.USE_PAIRING_ENGINE
                | AuthAction.MANUALLY_PAIR_PLAYERS
                | AuthAction.UNPAIR_ROUND
                | AuthAction.UNPAIR_BOARD
                | AuthAction.PERMUTE_BOARD
                | AuthAction.SET_CURRENT_ROUND
                | AuthAction.SET_ZPB
                | AuthAction.SET_HPB
                | AuthAction.SET_FPB
            ):
                return AuthActionCategory.PAIRINGS
            case (
                AuthAction.ENTER_RESULTS
                | AuthAction.UPDATE_RESULTS
                | AuthAction.SET_ILLEGAL_MOVES
                | AuthAction.SET_SPECIAL_RESULTS
            ):
                return AuthActionCategory.RESULTS
            case (
                AuthAction.MANAGE_SCREENS
                | AuthAction.VIEW_PRIVATE_SCREENS
                | AuthAction.VIEW_PUBLIC_SCREENS
            ):
                return AuthActionCategory.SCREENS
            case AuthAction.VIEW_PRIZES_TAB | AuthAction.MANAGE_PRIZES:
                return AuthActionCategory.PRIZES
            case AuthAction.GENERATE_DOCUMENTS:
                return AuthActionCategory.DOCUMENTS
            case _:
                raise ValueError(f'auth={self}')

    @property
    def name(self) -> str:
        return self.localized_name()

    def localized_name(self, locale: str | None = None) -> str:
        match self:
            case AuthAction.MANAGE_APPLICATION_SETTINGS:
                return _('Manage application settings', locale)
            case AuthAction.MANAGE_SOURCE_DATABASES:
                return _('Manage source databases', locale)
            case AuthAction.MANAGE_ARCHIVES:
                return _('Manage archives', locale)
            case AuthAction.VIEW_PRIVATE_EVENTS:
                return _('View private events', locale)
            case AuthAction.VIEW_PASSED_EVENTS:
                return _('View passed events', locale)
            case AuthAction.VIEW_DETAILED_EVENT_CARDS:
                return _('View event cards details', locale)
            case AuthAction.CREATE_EVENTS:
                return _('Create events', locale)
            case AuthAction.MANAGE_EVENTS:
                return _('Manage events', locale)
            case AuthAction.RENAME_EVENT:
                return _('Rename event', locale)
            case AuthAction.UPDATE_EVENT:
                return _('Update event', locale)
            case AuthAction.VIEW_EVENT_CONFIG:
                return _('View event configuration', locale)
            case AuthAction.MANAGE_ACCOUNTS:
                return _('Manage accounts', locale)
            case AuthAction.VIEW_TOURNAMENTS_TAB:
                return _('View the Tournaments tab', locale)
            case AuthAction.ADD_TOURNAMENTS:
                return _('Add tournaments', locale)
            case AuthAction.UPDATE_TOURNAMENTS:
                return _('Update tournaments', locale)
            case AuthAction.DELETE_TOURNAMENTS:
                return _('Delete tournaments', locale)
            case AuthAction.PUBLISH_RESULTS:
                return _('Publish tournament results', locale)
            case AuthAction.PUBLISH_RULES:
                return _('Publish tournament rules', locale)
            case AuthAction.DOWNLOAD_FEES:
                return _('Download tournament fees', locale)
            case AuthAction.VIEW_PLAYERS_TAB:
                return _('View Players tab', locale)
            case AuthAction.ADD_PLAYERS:
                return _('Add players', locale)
            case AuthAction.UPDATE_PLAYERS:
                return _('Update players', locale)
            case AuthAction.UPDATE_PLAYERS_HISTORY:
                return _("Update players' history", locale)
            case AuthAction.DELETE_PLAYERS:
                return _('Delete players', locale)
            case AuthAction.DISTRIBUTE_PLAYERS:
                return _('Distribute the players among the tournaments', locale)
            case AuthAction.OPEN_CLOSE_CHECK_IN:
                return _('Open/close check-in', locale)
            case AuthAction.CHECK_IN_PLAYERS:
                return _('Check-in players', locale)
            case AuthAction.VIEW_PAIRINGS_TAB:
                return _('View Pairings tab', locale)
            case AuthAction.USE_PAIRING_ENGINE:
                return _('Use pairing engines', locale)
            case AuthAction.MANUALLY_PAIR_PLAYERS:
                return _('Manually pair players', locale)
            case AuthAction.UNPAIR_ROUND:
                return _('Unpair all the boards of a round', locale)
            case AuthAction.UNPAIR_BOARD:
                return _('Unpair one board', locale)
            case AuthAction.PERMUTE_BOARD:
                return _('Permute boards', locale)
            case AuthAction.SET_CURRENT_ROUND:
                return _('Set the current round', locale)
            case AuthAction.SET_ZPB:
                return _('Set Zero-Points Byes', locale)
            case AuthAction.SET_HPB:
                return _('Set Half-Points Byes', locale)
            case AuthAction.SET_FPB:
                return _('Set Full-Points Byes', locale)
            case AuthAction.ENTER_RESULTS:
                return _('Enter results', locale)
            case AuthAction.UPDATE_RESULTS:
                return _('Update results', locale)
            case AuthAction.SET_ILLEGAL_MOVES:
                return _('Set illegal moves', locale)
            case AuthAction.SET_SPECIAL_RESULTS:
                return _('Set special results', locale)
            case AuthAction.MANAGE_SCREENS:
                return _('Manage screens', locale)
            case AuthAction.VIEW_PRIVATE_SCREENS:
                return _('View private screens', locale)
            case AuthAction.VIEW_PUBLIC_SCREENS:
                return _('View public screens', locale)
            case AuthAction.VIEW_PRIZES_TAB:
                return _('View Prizes tab', locale)
            case AuthAction.MANAGE_PRIZES:
                return _('Manage prizes', locale)
            case AuthAction.GENERATE_DOCUMENTS:
                return _('Generate documents', locale)
            case _:
                raise ValueError(f'auth={self}')
