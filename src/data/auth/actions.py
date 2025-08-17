from enum import StrEnum, auto

from common.i18n import _


class AuthActionCategory(StrEnum):
    APPLICATION = auto()
    EVENTS = auto()
    ACCESS = auto()
    TOURNAMENTS = auto()
    PLAYERS = auto()
    CHECK_IN = auto()
    PAIRINGS = auto()
    RANKINGS = auto()
    RESULTS = auto()
    SCREENS = auto()
    PRIZES = auto()
    PRINT = auto()

    @property
    def name(self) -> str:
        match self:
            case AuthActionCategory.APPLICATION:
                return _('Application management')
            case AuthActionCategory.EVENTS:
                return _('Events management')
            case AuthActionCategory.ACCESS:
                return _('Access control')
            case AuthActionCategory.TOURNAMENTS:
                return _('Tournaments management')
            case AuthActionCategory.PLAYERS:
                return _('Players')
            case AuthActionCategory.CHECK_IN:
                return _('Check-in')
            case AuthActionCategory.PAIRINGS:
                return _('Pairings')
            case AuthActionCategory.RANKINGS:
                return _('Rankings')
            case AuthActionCategory.RESULTS:
                return _('Results')
            case AuthActionCategory.SCREENS:
                return _('Screens')
            case AuthActionCategory.PRIZES:
                return _('Prizes')
            case AuthActionCategory.PRINT:
                return _('Print')
            case _:
                raise ValueError(f'auth={self}')


class AuthAction(StrEnum):
    # Application
    VIEW_APPLICATION_SETTINGS = auto()
    UPDATE_APPLICATION_SETTINGS = auto()
    MANAGE_SOURCE_DATABASES = auto()

    # Events
    VIEW_PRIVATE_EVENTS = auto()
    VIEW_PASSED_COMING_EVENTS = auto()
    ADD_EVENTS = auto()
    VIEW_DETAILED_EVENT_CARDS = auto()
    DELETE_EVENTS = auto()
    RENAME_EVENTS = auto()
    UPDATE_EVENTS = auto()
    VIEW_EVENT_COMPLETE_CONFIG = auto()
    VIEW_EVENT_BASIC_CONFIG = auto()

    # Access
    MANAGE_ACCOUNTS = auto()
    MANAGE_DEVICES = auto()

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
    VIEW_DRAFT_PAIRINGS = auto()
    PUBLISH_PAIRINGS = auto()

    # Rankings
    VIEW_DRAFT_RANKINGS = auto()
    PUBLISH_RANKINGS = auto()

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

    # Print
    PRINT = auto()

    @property
    def category(self) -> AuthActionCategory:
        match self:
            case (
                AuthAction.VIEW_APPLICATION_SETTINGS
                | AuthAction.UPDATE_APPLICATION_SETTINGS
                | AuthAction.MANAGE_SOURCE_DATABASES
            ):
                return AuthActionCategory.APPLICATION
            case (
                AuthAction.VIEW_PRIVATE_EVENTS
                | AuthAction.VIEW_PASSED_COMING_EVENTS
                | AuthAction.ADD_EVENTS
                | AuthAction.VIEW_DETAILED_EVENT_CARDS
                | AuthAction.DELETE_EVENTS
                | AuthAction.RENAME_EVENTS
                | AuthAction.UPDATE_EVENTS
                | AuthAction.VIEW_EVENT_COMPLETE_CONFIG
                | AuthAction.VIEW_EVENT_BASIC_CONFIG
            ):
                return AuthActionCategory.EVENTS
            case AuthAction.MANAGE_ACCOUNTS | AuthAction.MANAGE_DEVICES:
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
            ):
                return AuthActionCategory.PLAYERS
            case AuthAction.OPEN_CLOSE_CHECK_IN | AuthAction.CHECK_IN_PLAYERS:
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
                | AuthAction.VIEW_DRAFT_PAIRINGS
                | AuthAction.PUBLISH_PAIRINGS
            ):
                return AuthActionCategory.PAIRINGS
            case AuthAction.VIEW_DRAFT_RANKINGS | AuthAction.PUBLISH_RANKINGS:
                return AuthActionCategory.RANKINGS
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
            case AuthAction.PRINT:
                return AuthActionCategory.PRINT
            case _:
                raise ValueError(f'auth={self}')

    @property
    def name(self) -> str:
        match self:
            case AuthAction.VIEW_APPLICATION_SETTINGS:
                return _('View application settings')
            case AuthAction.UPDATE_APPLICATION_SETTINGS:
                return _('Update application settings')
            case AuthAction.MANAGE_SOURCE_DATABASES:
                return _('Manage source databases')
            case AuthAction.VIEW_PRIVATE_EVENTS:
                return _('View private events')
            case AuthAction.VIEW_PASSED_COMING_EVENTS:
                return _('View passed and upcoming events')
            case AuthAction.ADD_EVENTS:
                return _('Add events')
            case AuthAction.VIEW_DETAILED_EVENT_CARDS:
                return _('View event cards details')
            case AuthAction.DELETE_EVENTS:
                return _('Delete events')
            case AuthAction.RENAME_EVENTS:
                return _('Rename events')
            case AuthAction.UPDATE_EVENTS:
                return _('Update events')
            case AuthAction.VIEW_EVENT_COMPLETE_CONFIG:
                return _('View complete event configuration')
            case AuthAction.VIEW_EVENT_BASIC_CONFIG:
                return _('View basic event configuration')
            case AuthAction.MANAGE_ACCOUNTS:
                return _('Manage accounts')
            case AuthAction.MANAGE_DEVICES:
                return _('Manage devices')
            case AuthAction.VIEW_TOURNAMENTS_TAB:
                return _('View the Tournaments tab')
            case AuthAction.ADD_TOURNAMENTS:
                return _('Add tournaments')
            case AuthAction.UPDATE_TOURNAMENTS:
                return _('Update tournaments')
            case AuthAction.DELETE_TOURNAMENTS:
                return _('Delete tournaments')
            case AuthAction.PUBLISH_RESULTS:
                return _('Publish tournament results')
            case AuthAction.PUBLISH_RULES:
                return _('Publish tournament rules')
            case AuthAction.DOWNLOAD_FEES:
                return _('Download tournament fees')
            case AuthAction.VIEW_PLAYERS_TAB:
                return _('View Players tab')
            case AuthAction.ADD_PLAYERS:
                return _('Add players')
            case AuthAction.UPDATE_PLAYERS:
                return _('Update players')
            case AuthAction.UPDATE_PLAYERS_HISTORY:
                return _("Update players' history")
            case AuthAction.DELETE_PLAYERS:
                return _('Delete players')
            case AuthAction.OPEN_CLOSE_CHECK_IN:
                return _('Open/close check-in')
            case AuthAction.CHECK_IN_PLAYERS:
                return _('Check-in players')
            case AuthAction.VIEW_PAIRINGS_TAB:
                return _('View Pairings tab')
            case AuthAction.USE_PAIRING_ENGINE:
                return _('Use pairing engines')
            case AuthAction.MANUALLY_PAIR_PLAYERS:
                return _('Manually pair players')
            case AuthAction.UNPAIR_ROUND:
                return _('Upair all the boards of a round')
            case AuthAction.UNPAIR_BOARD:
                return _('Unpair one board')
            case AuthAction.PERMUTE_BOARD:
                return _('Permute boards')
            case AuthAction.SET_CURRENT_ROUND:
                return _('Set the current round')
            case AuthAction.SET_ZPB:
                return _('Set Zero-Points Byes')
            case AuthAction.SET_HPB:
                return _('Set Half-Points Byes')
            case AuthAction.SET_FPB:
                return _('Set Full-Points Byes')
            case AuthAction.VIEW_DRAFT_PAIRINGS:
                return _('View draft pairings')
            case AuthAction.PUBLISH_PAIRINGS:
                return _('Publish pairings')
            case AuthAction.VIEW_DRAFT_RANKINGS:
                return _('View draft rankings')
            case AuthAction.PUBLISH_RANKINGS:
                return _('Publish rankings')
            case AuthAction.ENTER_RESULTS:
                return _('Enter results')
            case AuthAction.UPDATE_RESULTS:
                return _('Update results')
            case AuthAction.SET_ILLEGAL_MOVES:
                return _('Set illegal moves')
            case AuthAction.SET_SPECIAL_RESULTS:
                return _('Set special results')
            case AuthAction.MANAGE_SCREENS:
                return _('Manage screens')
            case AuthAction.VIEW_PRIVATE_SCREENS:
                return _('View private screens')
            case AuthAction.VIEW_PUBLIC_SCREENS:
                return _('View public screens')
            case AuthAction.VIEW_PRIZES_TAB:
                return _('View Prizes tab')
            case AuthAction.MANAGE_PRIZES:
                return _('Manage prizes')
            case AuthAction.PRINT:
                return _('Print')
            case _:
                raise ValueError(f'auth={self}')
