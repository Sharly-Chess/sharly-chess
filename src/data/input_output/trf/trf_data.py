from collections import defaultdict
from functools import cached_property

from dataclasses import dataclass, field


TRF_DATE_FORMAT = '%Y/%m/%d'


@dataclass
class TrfGame:
    opponent_id: int | None
    color: str
    result: str
    round: int


@dataclass
class TrfNationalPlayer:
    player_id: int
    name: str = ''
    gender: str = ''
    classification: str = ''
    rating: int = 0
    origin: str = ''
    national_id: str = ''
    birth_date: str = ''


@dataclass
class TrfPlayer:
    id: int
    name: str = ''
    gender: str = 'm'
    title: str = ''
    rating: int = 0
    federation: str = ''
    fide_id: int | None = None
    birth_date: str = ''
    points: float = 0
    rank: int | None = None
    games: list[TrfGame] = field(default_factory=list)
    national_player_by_federation: dict[str, TrfNationalPlayer] = field(
        default_factory=dict
    )


@dataclass
class TrfTeam:
    id: int = 0
    name: str = ''
    nickname: str = ''
    strength_factor: int = 0
    match_points: float = 0.0
    game_points: float = 0.0
    rank: int | None = None
    player_ids: list[int] = field(default_factory=list)


@dataclass
class TrfDeprecatedTeam:
    name: str = ''
    player_ids: list[int] = field(default_factory=list)


@dataclass
class TrfRoundBye:
    type: str
    round: int
    pairing_numbers: list[int]


@dataclass
class TrfAcceleratedRound:
    match_points: float | None
    game_points: float | None
    first_round: int
    last_round: int
    first_id: int
    last_id: int


@dataclass
class TrfProhibitedPairing:
    first_round: int
    last_round: int | None
    pairing_numbers: list[int]


@dataclass
class TrfTeamPABs:
    match_points: float | None
    game_points: float
    team_id_by_round: dict[int, int]


@dataclass
class TrfTeamForfeitedMatch:
    type: str
    round: int
    white_team_id: int
    black_team_id: int


@dataclass
class TrfOOdOTeamPairing:
    round: int
    team_id: int
    opponent_team_id: int
    boards: list[int | None]


@dataclass
class TrfAbnormalPointsAssignment:
    type: str
    match_points: float
    game_points: float | None
    round: int | None
    pairing_numbers: list[int | None]


@dataclass
class TrfTournament:
    name: str = ''
    city: str = ''
    federation: str = ''
    start_date: str = ''
    end_date: str = ''
    num_players: int = 0
    num_rated_players: int = 0
    num_teams: int = 0
    type: str = ''
    encoded_type: str = ''
    chief_arbiter: str = ''
    deputy_arbiters: list[str] = field(default_factory=list)
    allotted_time: str = ''
    time_control: str = ''
    round_dates: list[str] = field(default_factory=list)
    num_rounds: int = 0
    initial_color: str = ''
    individuals_point_system: dict[str, float] = field(default_factory=dict)
    teams_point_system: dict[str, float] = field(default_factory=dict)
    starting_rank_method: str = ''
    pairing_controller_id: str = ''
    tie_breaks: list[str] = field(default_factory=list)
    standings_tie_breaks: list[str] = field(default_factory=list)
    board_color_sequence: str = ''

    teams: list[TrfTeam] = field(default_factory=list)
    deprecated_teams: list[TrfDeprecatedTeam] = field(default_factory=list)
    players: list[TrfPlayer] = field(default_factory=list)
    accelerated_rounds: list[TrfAcceleratedRound] = field(default_factory=list)
    prohibited_pairings: list[TrfProhibitedPairing] = field(default_factory=list)
    round_byes: list[TrfRoundBye] = field(default_factory=list)
    team_pabs: TrfTeamPABs | None = None
    team_forfeited_matches: list[TrfTeamForfeitedMatch] = field(default_factory=list)
    oodo_team_pairings: list[TrfOOdOTeamPairing] = field(default_factory=list)
    abnormal_points_assignments: list[TrfAbnormalPointsAssignment] = field(
        default_factory=list
    )
    informative_team_pairings_records: list[str] = field(default_factory=list)
    informative_team_results_records: list[str] = field(default_factory=list)

    xx_fields: dict[str, str] = field(default_factory=dict)
    bb_fields: dict[str, str] = field(default_factory=dict)

    @property
    def num_rounds_estimation(self):
        """An estimation of how many rounds where played in this tournament."""

        if self.num_rounds:
            return self.num_rounds

        if self.round_dates:
            return len(self.round_dates)

        return max(len(p.games) for p in self.players) or len(self.players) - 1

    @cached_property
    def national_players_by_federation(self) -> dict[str, list[TrfNationalPlayer]]:
        players_by_federation: dict[str, list[TrfNationalPlayer]] = defaultdict(list)
        for player in self.players:
            for (
                federation,
                national_player,
            ) in player.national_player_by_federation.items():
                players_by_federation[federation].append(national_player)
        return players_by_federation
