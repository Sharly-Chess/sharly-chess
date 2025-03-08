from dataclasses import dataclass, field

from common.papi_web_config import PapiWebConfig
from data.tie_break import TieBreak

"""
All the classes of this module are basic data classes store in the event databases.
"""


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
class StoredTournament:
    id: int | None
    uniq_id: str
    name: str
    path: str | None
    filename: str | None
    ffe_id: int | None
    ffe_password: str | None
    time_control_initial_time: int | None
    time_control_increment: int | None
    time_control_handicap_penalty_step: int | None
    time_control_handicap_penalty_value: int | None
    time_control_handicap_min_time: int | None
    chessevent_user_id: str | None
    chessevent_password: str | None
    chessevent_event_id: str | None
    chessevent_tournament_name: str | None
    record_illegal_moves: int | None
    rules: str | None
    first_board_number: int | None
    paired_bye_result: int | None
    max_byes: int | None
    last_rounds_no_byes: int | None
    tie_breaks: list[TieBreak] | None
    check_in_open: bool = field(default=False)
    last_update: float = field(default=0.0)
    last_result_update: float = field(default=0.0)
    last_illegal_move_update: float = field(default=0.0)
    last_check_in_update: float = field(default=0.0)
    last_ffe_upload: float = field(default=0.0)
    last_ffe_rules_upload: float = field(default=0.0)
    last_chessevent_download_md5: str | None = field(default=None)
    errors: dict[str, str] = field(default_factory=dict[str, str])


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
    menu_link: bool | None
    menu_text: str | None
    menu: str | None
    timer_id: int | None
    input_exit_button: bool | None
    players_show_unpaired: bool | None
    results_limit: int | None
    results_max_age: int | None
    background_image: str | None
    background_color: str | None
    results_tournament_ids: list[int] = field(default_factory=list[int])
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
    menu_link: bool
    menu_text: str
    menu: str
    timer_id: int | None
    input_exit_button: bool | None
    players_show_unpaired: bool | None
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
class StoredEvent:
    uniq_id: str
    name: str
    federation: str
    start: float
    stop: float
    public: bool = False
    path: str | None = None
    hide_background_image: bool = PapiWebConfig.default_hide_background_image
    background_image: str | None = None
    background_color: str | None = None
    update_password: str | None = None
    record_illegal_moves: int | None = None
    rules: str | None = None
    version: str | None = None
    timer_colors: dict[int, str | None] = None
    timer_delays: dict[int, int | None] = None
    message_text: str | None = None
    message_color: str | None = None
    message_background_color: str | None = None
    chessevent_user_id: str | None = None
    chessevent_password: str | None = None
    chessevent_event_id: str | None = None
    last_update: float = 0.0
    stored_timers: list[StoredTimer] = field(default_factory=list[StoredTimer])
    stored_tournaments: list[StoredTournament] = field(
        default_factory=list[StoredTournament]
    )
    stored_screens: list[StoredScreen] = field(default_factory=list[StoredScreen])
    stored_families: list[StoredFamily] = field(default_factory=list[StoredFamily])
    stored_rotators: list[StoredRotator] = field(default_factory=list[StoredRotator])
    errors: dict[str, str] = field(default_factory=dict[str, str])


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
