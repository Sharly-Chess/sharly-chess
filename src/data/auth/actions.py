from enum import StrEnum, auto


class AuthAction(StrEnum):
    # Application
    VIEW_APPLICATION_SETTINGS = auto()
    UPDATE_APPLICATION_SETTINGS = auto()
    MANAGE_SOURCE_DATABASES = auto()

    # Events
    VIEW_PRIVATE_EVENTS = auto()
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
