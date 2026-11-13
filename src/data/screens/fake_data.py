"""Made-up data for setting up the screens before the tournaments start.

While an event's screens show fake data, every individual tournament that has
no pairings yet is shown with a first round among its players, paired as its
pairing system would pair it, with a result on every board so that the ranking
counts the round.

The data only lives in the event loaded for the request: nothing is written.
"""

from __future__ import annotations

from datetime import datetime
from operator import attrgetter
from typing import TYPE_CHECKING

from database.sqlite.event.event_store import (
    StoredBoard,
    StoredPairing,
    StoredTournament,
)
from utils.enum import Result

if TYPE_CHECKING:
    from data.event import Event
    from data.pairings.systems import ExamplePair
    from data.player import TournamentPlayer
    from data.tournament import Tournament

#: The routes drawing a screen, which show the fake data. The routes entering
#: something through a screen keep to the real event.
FAKE_DATA_PATHS = (
    '/view/screen/',
    '/view/display-controller/',
    '/view/menu/',
    '/view/rotator/',
    '/view/paged-screen/',
)

#: The byes a player may already have been given for the first round.
_BYES = {
    Result.ZERO_POINT_BYE.value,
    Result.HALF_POINT_BYE.value,
    Result.FULL_POINT_BYE.value,
}

#: The made-up results of the boards, white's side, in turn.
_WHITE_RESULTS = (Result.WIN, Result.DRAW, Result.LOSS)
_DECISIVE_WHITE_RESULTS = (Result.WIN, Result.LOSS)


def tournaments_for_fake_data(event: Event) -> list[Tournament]:
    """The tournaments fake data can be shown for: the individual ones with
    players and no pairings yet."""
    return [
        tournament
        for tournament in event.tournaments_by_id.values()
        if not tournament.is_team_tournament
        and not tournament.stored_tournament.stored_boards_by_round
        and len(tournament.tournament_players) >= 2
    ]


def event_with_fake_data(event: Event) -> Event:
    """The event with a made-up first round for each individual tournament
    without pairings, or the event itself when there is none."""
    from data.event import Event

    fake_tournament_ids: set[int] = set()
    for tournament in tournaments_for_fake_data(event):
        stored_tournament = tournament.stored_tournament
        # Players already given a bye for the first round keep it; the others
        # lose whatever empty pairing they had for it.
        players: list[TournamentPlayer] = []
        for player in tournament.tournament_players:
            stored_pairings = player.stored_tournament_player.stored_pairings
            if any(
                pairing.round_ == 1 and pairing.result in _BYES
                for pairing in stored_pairings
            ):
                continue
            stored_pairings[:] = [
                pairing for pairing in stored_pairings if pairing.round_ != 1
            ]
            players.append(player)
        players.sort(key=attrgetter('starting_rank_sort_key'))
        if len(players) < 2:
            continue
        _pair_first_round(
            stored_tournament,
            players,
            tournament.pairing_system.example_first_round(players),
            tournament.pairing_system.example_draws,
        )
        fake_tournament_ids.add(tournament.id)
    if not fake_tournament_ids:
        return event
    fake_event = Event(event.stored_event, public_view=event.public_view)
    fake_event.fake_tournament_ids = fake_tournament_ids
    return fake_event


def _pair_first_round(
    stored_tournament: StoredTournament,
    players: list[TournamentPlayer],
    pairs: list[ExamplePair],
    draws: bool,
) -> None:
    """Seats the pairs of the example round, alternating colours, giving
    every game a result."""
    white_results = _WHITE_RESULTS if draws else _DECISIVE_WHITE_RESULTS
    now = datetime.now()
    boards: list[StoredBoard] = []
    for index, (higher, lower) in enumerate(pairs):
        board_id = index + 1
        if lower is None:
            boards.append(
                StoredBoard(
                    id=board_id,
                    white_player_id=higher.id,
                    black_player_id=None,
                    index=index,
                )
            )
            _add_pairing(
                stored_tournament, higher, Result.PAIRING_ALLOCATED_BYE, board_id
            )
            continue
        white, black = (higher, lower) if index % 2 == 0 else (lower, higher)
        white_result = white_results[index % len(white_results)]
        boards.append(
            StoredBoard(
                id=board_id,
                white_player_id=white.id,
                black_player_id=black.id,
                index=index,
                last_result_update=now,
            )
        )
        _add_pairing(stored_tournament, white, white_result, board_id)
        _add_pairing(stored_tournament, black, white_result.opposite_result, board_id)
    stored_tournament.stored_boards_by_round[1] = boards
    stored_tournament.published_round = max(stored_tournament.published_round, 1)


def _add_pairing(
    stored_tournament: StoredTournament,
    player: TournamentPlayer,
    result: Result,
    board_id: int,
) -> None:
    player.stored_tournament_player.stored_pairings.append(
        StoredPairing(
            tournament_id=stored_tournament.id or 0,
            player_id=player.id,
            round_=1,
            result=result.value,
            board_id=board_id,
        )
    )
