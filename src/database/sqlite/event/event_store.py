"""
All the classes of this module are basic data classes stored in the event databases.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


from common.sharly_chess_config import SharlyChessConfig
from utils.enum import Result


@dataclass
class StoredTimerHour:
    id: int | None
    uniq_id: str
    timer_id: int
    triggered_at: datetime
    text_before: str | None = None
    text_after: str | None = None
    errors: dict[str, str] = field(default_factory=dict[str, str])


@dataclass
class StoredTimer:
    id: int | None
    name: str
    colors: dict[int, str | None]
    delays: dict[int, int | None]
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
    type: str
    value: float
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
class StoredTournamentCriterion:
    id: int | None
    tournament_id: int
    type: str
    options: dict[str, Any]


@dataclass
class StoredTieBreak:
    id: int | None
    tournament_id: int
    type: str
    options: dict[str, Any]
    index: int


@dataclass
class StoredPairing:
    tournament_id: int
    player_id: int
    round_: int
    result: int
    board_id: int | None
    illegal_moves: int = 0


@dataclass
class StoredBoard:
    id: int | None
    white_player_id: int
    black_player_id: int | None
    index: int
    last_result_update: float | None = None


@dataclass
class StoredTournamentPlayer:
    tournament_id: int = 0
    player_id: int = 0
    pairing_number: int | None = None
    manual_tiebreak: int | None = None
    stored_pairings: list[StoredPairing] = field(default_factory=list[StoredPairing])


@dataclass
class StoredPlayer:
    id: int | None
    last_name: str
    ratings: dict[int, dict[str, int | None]]
    first_name: str | None = None
    date_of_birth: date | None = None
    year_of_birth: int | None = None
    gender: str = ''
    mail: str | None = None
    phone: str | None = None
    comment: str | None = None
    owed: float = 0.0
    paid: float = 0.0
    title: str = ''
    fide_id: int | None = None
    federation: str = 'FID'
    club: str | None = None
    fixed: int | None = None
    check_in: bool = False

    plugin_data: dict[str, dict[str, Any]] = field(
        default_factory=dict[str, dict[str, Any]]
    )


@dataclass
class StoredTournament:
    id: int | None
    name: str
    index: int = 0
    time_control_trf25: str | None = None
    record_illegal_moves: int | None = None
    rules: str | None = None
    first_board_number: int | None = None
    paired_bye_result: int | None = None
    max_byes: int | None = None
    last_rounds_no_byes: int | None = None
    location: str | None = None
    start_date: date | None = None
    stop_date: date | None = None
    pairing: str = SharlyChessConfig.default_pairing_variation_id
    pairing_settings: dict[str, Any] = field(default_factory=dict[str, Any])
    current_round: int | None = None
    check_in_open: bool = False
    rounds: int = 1
    rating: int = 1
    player_rating_type: int | None = None
    last_update: float = 0.0
    last_player_update: float = 0.0
    last_pairing_update: float = 0.0
    three_points_for_a_win: bool = False
    override_unrated_rapid_blitz: bool = True
    pab_value: int = Result.WIN.value
    stored_tie_breaks: list[StoredTieBreak] = field(
        default_factory=list[StoredTieBreak]
    )
    stored_criteria: list[StoredTournamentCriterion] = field(
        default_factory=list[StoredTournamentCriterion]
    )
    stored_prize_groups: list[StoredPrizeGroup] = field(
        default_factory=list[StoredPrizeGroup]
    )

    stored_tournament_players: list[StoredTournamentPlayer] = field(
        default_factory=list[StoredTournamentPlayer]
    )

    stored_boards_by_round: dict[int, list[StoredBoard]] = field(
        default_factory=dict[int, list[StoredBoard]]
    )

    # Plugins can add their own tournament data
    plugin_data: dict[str, dict[str, Any]] = field(
        default_factory=dict[str, dict[str, Any]]
    )


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
    players_player_format: int | None
    players_board_format: int | None
    players_opponent_format: int | None
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
    players_player_format: int | None
    players_board_format: int | None
    players_opponent_format: int | None
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
class StoredRotatingScreen:
    id: int | None
    rotator_id: int
    screen_id: int | None = None
    family_id: int | None = None
    index: int = 0


@dataclass
class StoredRotator:
    id: int | None
    name: str
    delay: int | None = None
    public: bool = True
    message_default: bool = True
    message_text: str | None = None
    timer_id: int | None = None
    stored_rotating_screens: list[StoredRotatingScreen] = field(
        default_factory=list[StoredRotatingScreen]
    )


@dataclass
class StoredDisplayController:
    id: int | None
    name: str
    public: bool = True
    screen_id: int | None = None
    rotator_id: int | None = None
    errors: dict[str, str] = field(default_factory=dict[str, str])


@dataclass
class StoredPermission:
    account_id: int
    access_level: str
    tournament_ids: list[int] | None = None


@dataclass
class StoredRole:
    account_id: int | None
    role: str
    tournament_ids: list[int] | None = None


@dataclass
class StoredAccount:
    id: int | None
    active: bool
    first_name: str | None
    last_name: str | None
    fide_id: int | None = None
    fide_arbiter_title: str | None = None
    password_hash: str | None = None
    mail: str | None = None
    phone: str | None = None
    stored_permissions: list[StoredPermission] = field(
        default_factory=list[StoredPermission]
    )
    stored_roles: list[StoredRole] = field(default_factory=list[StoredRole])
    # Plugins can add their own tournament data
    plugin_data: dict[str, dict[str, Any]] = field(
        default_factory=dict[str, dict[str, Any]]
    )


@dataclass
class BaseStoredEvent:
    uniq_id: str
    name: str
    federation: str
    player_rating_type: int
    start_date: date
    stop_date: date
    public: bool = False
    location: str | None = None
    background_color: str | None = None
    timer_colors: dict[int, str | None] = field(default_factory=dict[int, str | None])
    timer_delays: dict[int, int | None] = field(default_factory=dict[int, int | None])
    message_text: str | None = None
    message_color: str | None = None
    message_background_color: str | None = None
    prize_currency: str | None = None
    age_category_base_date: date | None = None
    age_category_change_month: int = 1
    age_categories: list[str] | None = None
    organiser_name: str | None = None
    organiser_home_page: str | None = None
    organiser_email: str | None = None
    organiser_director: str | None = None

    # Plugins can add their own event data
    plugin_data: dict[str, dict[str, Any]] = field(
        default_factory=dict[str, dict[str, Any]]
    )
    enabled_plugins: list[str] = field(default_factory=list[str])


@dataclass
class StoredEvent(BaseStoredEvent):
    stored_players: list[StoredPlayer] = field(default_factory=list[StoredPlayer])
    stored_tournaments: list[StoredTournament] = field(
        default_factory=list[StoredTournament]
    )
    stored_timers: list[StoredTimer] = field(default_factory=list[StoredTimer])
    stored_screens: list[StoredScreen] = field(default_factory=list[StoredScreen])
    stored_families: list[StoredFamily] = field(default_factory=list[StoredFamily])
    stored_rotators: list[StoredRotator] = field(default_factory=list[StoredRotator])
    stored_display_controllers: list[StoredDisplayController] = field(
        default_factory=list[StoredDisplayController]
    )
    stored_accounts: list[StoredAccount] = field(default_factory=list[StoredAccount])
