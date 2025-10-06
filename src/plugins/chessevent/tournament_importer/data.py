from dataclasses import dataclass, field

from utils.enum import PlayerGender, PlayerCategory, TournamentRating


@dataclass
class ChessEventPlayer:
    last_name: str
    first_name: str
    federation: str
    birth: int
    ffe_id: int
    ffe_license: int
    ffe_license_number: str
    ffe_league: str
    standard_rating: int
    standard_rating_type: int
    rapid_rating: int
    rapid_rating_type: int
    blitz_rating: int
    blitz_rating_type: int
    title: int
    email: str
    phone: str
    fee: int | float
    paid: int | float
    check_in: bool | int
    board: int
    fide_id: int = 0
    gender: PlayerGender = PlayerGender.NONE
    ffe_club_id: int = 0
    ffe_club: str = ''
    category: PlayerCategory = PlayerCategory.NONE
    skipped_rounds: dict[int, int | float] = field(
        default_factory=dict[int, int | float]
    )
    # TODO (Molrn) Add the fields: initial_fee, discount, paid_for, paid_site


@dataclass
class ChessEventTournament:
    name: str
    type: int
    rounds: int
    pairing: int
    time_control: str
    location: str
    arbiter: str
    start: int
    end: int
    tie_break_1: int | None
    tie_break_2: int | None
    tie_break_3: int | None
    players: list[ChessEventPlayer]
    rating: TournamentRating = TournamentRating.STANDARD
    ffe_id: int | None = None
