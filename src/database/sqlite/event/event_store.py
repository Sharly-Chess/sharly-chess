"""
All the classes of this module are basic data classes stored in the event databases.
"""

from abc import ABC
from dataclasses import dataclass, field
from typing import Any

from common.sharly_chess_config import SharlyChessConfig
from data.auth.roles import Role


@dataclass
class StoredTimerHour:
    id: int | None
    uniq_id: str
    timer_id: int
    order: int | None = None
    date_str: str | None = None
    time_str: str | None = None
    text_before: str | None = None
    text_after: str | None = None
    errors: dict[str, str] = field(default_factory=dict[str, str])


@dataclass
class StoredTimer:
    id: int | None
    uniq_id: str
    colors: dict[int, str | None] | None
    delays: dict[int, int | None] | None
    stored_timer_hours: list[StoredTimerHour] = field(
        default_factory=list[StoredTimerHour]
    )
    errors: dict[str, str] = field(default_factory=dict[str, str])


@dataclass
class StoredPrizeCriterion:
    id: int | None
    prize_category_id: int
    type: str
    options: dict[str, Any]


@dataclass
class StoredPrize:
    id: int | None
    prize_category_id: int
    value: float
    is_monetary: bool
    description: str


@dataclass
class StoredPrizeCategory:
    id: int | None
    prize_group_id: int
    name: str
    prize_sharing: str
    sharing_threshold: float | None
    is_main: bool
    index: int
    stored_prize_criteria: list[StoredPrizeCriterion] = field(
        default_factory=list[StoredPrizeCriterion]
    )
    stored_prizes: list[StoredPrize] = field(default_factory=list[StoredPrize])


@dataclass
class StoredPrizeGroup:
    id: int | None
    tournament_id: int
    name: str
    stored_prize_categories: list[StoredPrizeCategory] = field(
        default_factory=list[StoredPrizeCategory]
    )


@dataclass
class StoredTournament:
    id: int | None
    uniq_id: str
    name: str
    path: str | None
    filename: str | None
    time_control_initial_time: int | None = None
    time_control_increment: int | None = None
    time_control_handicap_penalty_step: int | None = None
    time_control_handicap_penalty_value: int | None = None
    time_control_handicap_min_time: int | None = None
    record_illegal_moves: int | None = None
    rules: str | None = None
    first_board_number: int | None = None
    paired_bye_result: int | None = None
    max_byes: int | None = None
    last_rounds_no_byes: int | None = None
    tie_breaks: list[dict[str, str | dict[str, Any]]] | None = None
    location: str | None = None
    start: float | None = None
    stop: float | None = None
    pairing: str | None = None
    pairing_settings: dict[str, Any] | None = None
    current_round: int | None = None
    check_in_open: bool = field(default=False)
    rounds: int = field(default=1)
    rating: int = field(default=1)
    last_update: float = field(default=0.0)
    last_result_update: float = field(default=0.0)
    last_illegal_move_update: float = field(default=0.0)
    last_check_in_update: float = field(default=0.0)
    stored_prize_groups: list[StoredPrizeGroup] = field(
        default_factory=list[StoredPrizeGroup]
    )
    errors: dict[str, str] = field(default_factory=dict[str, str])

    # Plugins can add their own tournament data
    plugin_data: dict[str, dict[str, Any]] | None = None


@dataclass
class StoredScreenSet:
    id: int | None
    screen_id: int
    tournament_id: int
    name: str | None
    order: int | None
    fixed_boards_str: str | None
    first: int | None
    last: int | None
    last_update: float = 0.0
    errors: dict[str, str] = field(default_factory=dict[str, str])


@dataclass
class StoredScreen:
    id: int | None
    uniq_id: str
    name: str | None
    type: str
    columns: int | None
    font_size: int | None
    menu_link: bool | None
    menu_text: str | None
    menu: str | None
    timer_id: int | None
    input_exit_button: bool | None
    players_show_unpaired: bool | None
    players_show_opponent: bool | None
    results_limit: int | None
    results_max_age: int | None
    background_image: str | None
    background_color: str | None
    results_tournament_ids: list[int] = field(default_factory=list[int])
    ranking_crosstable: bool = False
    ranking_round: int | None = None
    ranking_min_points: float | None = None
    ranking_max_points: float | None = None
    stored_screen_sets: list[StoredScreenSet] = field(
        default_factory=list[StoredScreenSet]
    )
    last_update: float = 0.0
    public: bool = True
    message_default: bool = True
    message_text: str | None = None
    errors: dict[str, str] = field(default_factory=dict[str, str])
    init_set_tournament_id: int | None = None


@dataclass
class StoredFamily:
    id: int | None
    uniq_id: str
    name: str | None
    type: str
    tournament_id: int
    columns: int | None
    font_size: int | None
    menu_link: bool
    menu_text: str
    menu: str
    timer_id: int | None
    input_exit_button: bool | None
    players_show_unpaired: bool | None
    players_show_opponent: bool | None
    ranking_crosstable: bool
    ranking_round: int | None
    ranking_min_points: float | None
    ranking_max_points: float | None
    first: int | None
    last: int | None
    parts: int | None
    number: int | None
    public: bool = True
    message_default: bool = True
    message_text: str | None = None
    last_update: float = 0.0
    errors: dict[str, str] = field(default_factory=dict[str, str])


@dataclass
class StoredRotator:
    id: int | None
    uniq_id: str
    family_ids: list[int] | None
    screen_ids: list[int] | None
    delay: int | None
    public: bool = True
    message_default: bool = True
    message_text: str | None = None
    errors: dict[str, str] = field(default_factory=dict[str, str])


@dataclass
class StoredDisplayController:
    id: int | None
    uniq_id: str
    name: str | None
    public: bool = True
    errors: dict[str, str] = field(default_factory=dict[str, str])
    screen_id: int | None = None
    rotator_id: int | None = None


@dataclass
class StoredAccess(ABC):
    id: int | None
    edit_properties: bool
    edit_permissions: bool
    active: bool
    permissions: dict[int, str | None]


LOCALHOST_ID: int = -2
ANY_COMPUTER_ID: int = -1


@dataclass
class StoredComputer(StoredAccess):
    ip: str | None
    errors: dict[str, str] = field(default_factory=dict[str, str])


# computers are stored at event-level, this provides event-free
# instances that can be used when no events are available (welcome page, ...)
localhost_stored_computer: StoredComputer = StoredComputer(
    id=LOCALHOST_ID,
    edit_properties=False,
    edit_permissions=False,
    active=True,
    permissions={
        Role.ADMINISTRATOR: None,
    },
    ip=None,
)

unknown_stored_computer: StoredComputer = StoredComputer(
    id=ANY_COMPUTER_ID,
    edit_properties=False,
    edit_permissions=True,
    active=True,
    permissions={},
    ip=None,
)


ANONYMOUS_ID: int = -1


@dataclass
class StoredAccount(StoredAccess):
    username: str | None
    password: str | None
    errors: dict[str, str] = field(default_factory=dict[str, str])


# Accounts are stored at event-level, this provides an event-free
# instance that can be used when no events are available (welcome page, ...)
anonymous_stored_account: StoredAccount = StoredAccount(
    id=ANONYMOUS_ID,
    edit_properties=False,
    edit_permissions=True,
    active=True,
    permissions={},
    username=None,
    password=None,
)


@dataclass
class BaseStoredEvent:
    uniq_id: str
    name: str
    federation: str
    start: float
    stop: float
    public: bool = False
    path: str | None = None
    location: str | None = None
    hide_background_image: bool = SharlyChessConfig.default_hide_background_image
    background_image: str | None = None
    background_color: str | None = None
    update_password: str | None = None
    record_illegal_moves: int | None = None
    rules: str | None = None
    timer_colors: dict[int, str | None] | None = None
    timer_delays: dict[int, int | None] | None = None
    message_text: str | None = None
    message_color: str | None = None
    message_background_color: str | None = None
    prize_currency: str | None = None
    last_update: float = 0.0

    # Plugins can add their own tournament data
    plugin_data: dict[str, dict[str, Any]] | None = None


@dataclass
class StoredEvent(BaseStoredEvent):
    stored_timers: list[StoredTimer] = field(default_factory=list[StoredTimer])
    stored_tournaments: list[StoredTournament] = field(
        default_factory=list[StoredTournament]
    )
    stored_screens: list[StoredScreen] = field(default_factory=list[StoredScreen])
    stored_families: list[StoredFamily] = field(default_factory=list[StoredFamily])
    stored_rotators: list[StoredRotator] = field(default_factory=list[StoredRotator])
    stored_display_controllers: list[StoredDisplayController] = field(
        default_factory=list[StoredDisplayController]
    )
    stored_computers: list[StoredComputer] = field(default_factory=list[StoredComputer])
    stored_accounts: list[StoredAccount] = field(default_factory=list[StoredAccount])
    errors: dict[str, str] = field(default_factory=dict[str, str])


@dataclass
class EventMetadata(BaseStoredEvent):
    """Class containing the metadata of an event required
    for display on the event selection pages."""

    tournament_count: int = 0
    timer_count: int = 0
    screen_count: int = 0
    family_count: int = 0
    rotator_count: int = 0
    last_tournament_update: float | None = None


@dataclass
class StoredIllegalMove:
    id: int | None
    tournament_id: int
    round: int
    player_id: int
    date: float


@dataclass
class StoredResult:
    id: int | None
    tournament_id: int
    board_id: int
    result: int
    date: float
