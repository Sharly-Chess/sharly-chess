"""Made-up data for setting up the screens before the tournaments start.

While an event's screens show fake data, every tournament that has no
pairings yet is shown with a first round among its players, or among its teams
fielding their first-round lineups, paired as its pairing system would pair it,
with a result on every board so that the ranking counts the round.

The data only lives in the event loaded for the request: nothing is written.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from operator import attrgetter
from typing import TYPE_CHECKING

from common.exception import SharlyChessException
from database.sqlite.event.event_store import (
    StoredBoard,
    StoredPairing,
    StoredTeamBoard,
    StoredTournament,
)
from utils.enum import Result, TeamByeType

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
    """The tournaments fake data can be shown for: the ones with no pairings
    yet and at least two players, or two teams for a team tournament."""
    return [
        tournament
        for tournament in event.tournaments_by_id.values()
        if not tournament.stored_tournament.stored_boards_by_round
        and (
            _team_tournament_waits(tournament)
            if tournament.is_team_tournament
            else len(tournament.tournament_players) >= 2
        )
    ]


def _team_tournament_waits(tournament: Tournament) -> bool:
    """Whether a team tournament has two teams and no match paired yet, the
    byes given beforehand by the arbiter aside."""
    return len(tournament.teams) >= 2 and all(
        _is_manual_bye(stored_team_board)
        for stored_team_boards in (
            tournament.stored_tournament.stored_team_boards_by_round.values()
        )
        for stored_team_board in stored_team_boards
    )


def _is_manual_bye(stored_team_board: StoredTeamBoard) -> bool:
    return (
        stored_team_board.team_b_id is None
        and stored_team_board.bye_type in TeamByeType.manual_bye_types()
    )


def event_with_fake_data(event: Event) -> Event:
    """The event with a made-up first round for each tournament without
    pairings, or the event itself when there is none."""
    from data.event import Event

    fake_tournament_ids: set[int] = {
        tournament.id
        for tournament in tournaments_for_fake_data(event)
        if _fake_round(tournament)
    }
    if not fake_tournament_ids:
        return event
    fake_event = Event(event.stored_event, public_view=event.public_view)
    fake_event.fake_tournament_ids = fake_tournament_ids
    return fake_event


def _fake_round(tournament: Tournament) -> bool:
    """Pairs the first round of the tournament, telling whether it could."""
    if not tournament.is_team_tournament:
        return _fake_individual_round(tournament)
    if tournament.pairing_system.paired_by_team:
        return _fake_team_round(tournament)
    return _fake_flat_team_round(tournament)


def _fake_individual_round(tournament: Tournament) -> bool:
    """Pairs the first round of an individual tournament among its players,
    telling whether there were enough of them."""
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
        _drop_first_round(player)
        players.append(player)
    players.sort(key=attrgetter('starting_rank_sort_key'))
    if len(players) < 2:
        return False
    _pair_first_round(
        tournament.stored_tournament,
        players,
        tournament.pairing_system.example_first_round(players),
        tournament.pairing_system.example_draws,
    )
    return True


def _fake_team_round(tournament: Tournament) -> bool:
    """Pairs the first round of a team tournament among its teams, each
    fielding its first-round lineup, telling whether there were enough
    teams."""
    from data.pairings.engines import TeamPairingEngine

    engine = tournament.pairing_variation.engine
    if not isinstance(engine, TeamPairingEngine):
        return False
    stored_tournament = tournament.stored_tournament
    # Teams already given a bye for the first round keep it.
    byes = [
        stored_team_board
        for stored_team_board in stored_tournament.stored_team_boards_by_round.get(
            1, []
        )
        if _is_manual_bye(stored_team_board)
    ]
    bye_team_ids = {stored_team_board.team_a_id for stored_team_board in byes}
    teams = [
        team
        for team in engine._teams_for_tournament(tournament)
        if team.id not in bye_team_ids
    ]
    if len(teams) < 2:
        return False
    team_ids = {team.id for team in teams}
    for player in tournament.tournament_players:
        if player.team_id in team_ids:
            _drop_first_round(player)
    players_by_id = tournament.tournament_players_by_id
    white_results = _team_results(tournament.pairing_system.example_draws)
    now = datetime.now()
    next_team_board_id = (
        max(
            (stored_team_board.id or 0 for stored_team_board in byes),
            default=0,
        )
        + 1
    )
    team_boards: list[StoredTeamBoard] = list(byes)
    boards: list[StoredBoard] = []
    for index, (higher, lower) in enumerate(
        tournament.pairing_system.example_first_round(teams)
    ):
        team_a, team_b = (
            (higher, lower) if index % 2 == 0 or lower is None else (lower, higher)
        )
        stored_team_board = StoredTeamBoard(
            id=next_team_board_id + index,
            tournament_id=stored_tournament.id or 0,
            round_=1,
            team_a_id=team_a.id,
            team_b_id=team_b.id if team_b else None,
            index=index,
            last_result_update=now,
            bye_type=None if team_b else TeamByeType.PAB,
        )
        team_boards.append(stored_team_board)
        # The higher-ranked team wins one match, the lower-ranked one the next.
        winner_id = higher.id if index % 2 == 0 else lower.id if lower else None
        for board_index, stored_board in enumerate(
            engine._team_match_stored_boards(tournament, stored_team_board)
        ):
            board = replace(stored_board, id=len(boards) + 1, last_result_update=now)
            boards.append(board)
            white = players_by_id.get(board.white_player_id or 0)
            black = players_by_id.get(board.black_player_id or 0)
            if white is None or black is None:
                present = white or black
                if present is not None:
                    _add_pairing(
                        stored_tournament,
                        present,
                        engine.pab_result if team_b is None else Result.FORFEIT_WIN,
                        board.id or 0,
                    )
                continue
            winner_result = white_results[board_index % len(white_results)]
            white_result = (
                winner_result
                if white.team_id == winner_id
                else winner_result.opposite_result
            )
            _add_pairing(stored_tournament, white, white_result, board.id or 0)
            _add_pairing(
                stored_tournament, black, white_result.opposite_result, board.id or 0
            )
    stored_tournament.stored_team_boards_by_round[1] = team_boards
    stored_tournament.stored_boards_by_round[1] = boards
    stored_tournament.published_round = max(stored_tournament.published_round, 1)
    return True


def _fake_flat_team_round(tournament: Tournament) -> bool:
    """Pairs the first round of a team tournament whose boards are not
    grouped into matches, from its pairing table and the teams' first-round
    lineups, telling whether a table covers the teams."""
    engine = tournament.pairing_variation.engine
    try:
        stored_boards = engine._generate_stored_boards(tournament, 1)
    except SharlyChessException, ValueError:
        return False
    if not stored_boards:
        return False
    for player in tournament.tournament_players:
        _drop_first_round(player)
    stored_tournament = tournament.stored_tournament
    players_by_id = tournament.tournament_players_by_id
    white_results = (
        _WHITE_RESULTS
        if tournament.pairing_system.example_draws
        else _DECISIVE_WHITE_RESULTS
    )
    now = datetime.now()
    boards: list[StoredBoard] = []
    for index, stored_board in enumerate(stored_boards):
        board = replace(stored_board, id=index + 1, last_result_update=now)
        boards.append(board)
        white = players_by_id.get(board.white_player_id or 0)
        black = players_by_id.get(board.black_player_id or 0)
        if white is None or black is None:
            if present := white or black:
                _add_pairing(stored_tournament, present, engine.pab_result, index + 1)
            continue
        white_result = white_results[index % len(white_results)]
        _add_pairing(stored_tournament, white, white_result, index + 1)
        _add_pairing(stored_tournament, black, white_result.opposite_result, index + 1)
    stored_tournament.stored_boards_by_round[1] = boards
    stored_tournament.published_round = max(stored_tournament.published_round, 1)
    return True


def _team_results(draws: bool) -> tuple[Result, ...]:
    """The results of a match's boards in turn, from the side of the team
    winning it, which stays ahead whatever the number of boards."""
    if draws:
        return (Result.WIN, Result.DRAW, Result.WIN, Result.LOSS)
    return (Result.WIN, Result.WIN, Result.LOSS)


def _drop_first_round(player: TournamentPlayer) -> None:
    stored_pairings = player.stored_tournament_player.stored_pairings
    stored_pairings[:] = [pairing for pairing in stored_pairings if pairing.round_ != 1]


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
