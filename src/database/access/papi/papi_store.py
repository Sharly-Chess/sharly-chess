from dataclasses import dataclass, field
from datetime import date
from typing import Any

# TODO(Molrn - Big move) Move to the event store


@dataclass
class StoredPairing:
    tournament_id: int
    player_id: int
    round_: int
    result: int
    board_id: int | None


@dataclass
class StoredBoard:
    id: int | None
    white_player_id: int
    black_player_id: int | None
    index: int


@dataclass
class StoredTournamentPlayer:
    tournament_id: int = 0
    player_id: int = 0
    pairing_number: int | None = None
    stored_pairings: list[StoredPairing] = field(default_factory=list[StoredPairing])


@dataclass
class StoredPlayer:
    id: int | None
    last_name: str
    first_name: str | None
    date_of_birth: date | None
    gender: int
    mail: str | None
    phone: str | None
    comment: str | None
    owed: float
    paid: float
    title: int
    ratings: dict[int, dict[str, int]]
    fide_id: int | None
    federation: str
    club: str
    fixed: int | None
    check_in: bool
    # TODO (Molrn - multi tournament) move to a list in StoredTournament
    stored_tournament_player: StoredTournamentPlayer = field(
        default_factory=StoredTournamentPlayer
    )

    plugin_data: dict[str, dict[str, Any]] = field(
        default_factory=dict[str, dict[str, Any]]
    )
