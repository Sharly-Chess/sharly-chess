"""The grid of a round robin: every member against every other, each
encounter with its round and, once it may be shown, its result.

The rounds already paired are read from their pairings, the others from the
schedule the tournament is paired from, so that the grid shows when each
encounter takes place before it is played."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from data.pairings.engines import ScheduledRoundRobin, TeamRoundRobinPairingEngine
from utils import Utils
from utils.enum import Result

if TYPE_CHECKING:
    from data.player import TournamentPlayer
    from data.teams.team import Team
    from data.tournament import Tournament


@dataclass(frozen=True)
class GridEncounter:
    """One game, or match, between two members: the round it is played in,
    and its result from the side of the member whose row it is in, or None
    while it is not to be shown."""

    round: int
    result: str | None = None
    annulled: bool = False


type GridCells = dict[int, dict[int, list[GridEncounter]]]


def round_robin_engine(tournament: Tournament) -> ScheduledRoundRobin | None:
    """The engine pairing *tournament* from a round-robin schedule, None
    when the tournament is not a round robin."""
    engine = tournament.pairing_variation.engine
    return engine if isinstance(engine, ScheduledRoundRobin) else None


def members_by_pairing_number(tournament: Tournament) -> list[int]:
    """The ids of the members of *tournament*, players or teams, by Berger
    number."""
    engine = round_robin_engine(tournament)
    if engine is None:
        return []
    numbered = engine.berger_numbered_members(tournament)
    return [numbered[number] for number in sorted(numbered)]


def player_grid(
    tournament: Tournament, shows_result: Callable[[int], bool]
) -> GridCells:
    """The encounters of every two players of the round robin *tournament*,
    by player id and opponent id, in the order of the rounds. The result of
    a game is given when *shows_result* accepts its round."""
    engine = round_robin_engine(tournament)
    players = tournament.tournament_players_by_id
    cells: GridCells = {
        player_id: {
            opponent_id: [] for opponent_id in players if opponent_id != player_id
        }
        for player_id in players
    }
    if engine is None:
        return cells
    schedule = engine.schedule(tournament)
    for round_ in range(1, tournament.rounds + 1):
        tables, _rests = engine.paired_tables(tournament, round_)
        if not tables and schedule is not None and round_ in schedule.rounds:
            tables = schedule.rounds[round_].tables
        for white_id, black_id in tables:
            if white_id is None or black_id is None:
                continue
            for player_id, opponent_id in ((white_id, black_id), (black_id, white_id)):
                if player_id not in cells or opponent_id not in cells[player_id]:
                    continue
                player = players[player_id]
                pairing = player.pairings_by_round.get(round_)
                if (
                    pairing is None
                    or pairing.opponent_id != opponent_id
                    or pairing.result == Result.NO_RESULT
                    or not shows_result(round_)
                ):
                    encounter = GridEncounter(round_)
                else:
                    encounter = GridEncounter(
                        round_,
                        pairing.result.to_berger_table,
                        player.game_is_annulled(pairing),
                    )
                cells[player_id][opponent_id].append(encounter)
    return cells


def team_grid(tournament: Tournament, shows_result: Callable[[int], bool]) -> GridCells:
    """The matches of every two teams of the team round robin *tournament*,
    by team id and opponent id, in the order of the rounds. A match shows
    its outcome for the team of the row (1, ½, 0, or F for a team forfeiting
    the whole match), decided on the effective game points as the standings
    are, once *shows_result* accepts its round."""
    engine = tournament.pairing_variation.engine
    team_ids = [team.id for team in tournament.teams]
    cells: GridCells = {
        team_id: {opponent_id: [] for opponent_id in team_ids if opponent_id != team_id}
        for team_id in team_ids
    }
    if not isinstance(engine, TeamRoundRobinPairingEngine):
        return cells
    boards_by_round_pair = {
        (
            round_,
            frozenset({team_board.stored_team_board.team_a_id, team_b_id}),
        ): team_board
        for round_ in range(1, tournament.rounds + 1)
        for team_board in tournament.get_round_team_boards(round_)
        if (team_b_id := team_board.stored_team_board.team_b_id) is not None
    }
    for round_, pairs in engine.full_schedule(tournament).items():
        for a_id, b_id in pairs:
            if b_id is None:
                continue
            match = boards_by_round_pair.get((round_, frozenset({a_id, b_id})))
            played = (
                match is not None
                and match.match_score_pair is not None
                and shows_result(round_)
            )
            for mine, theirs in ((a_id, b_id), (b_id, a_id)):
                if mine not in cells or theirs not in cells[mine]:
                    continue
                score: str | None = None
                if played:
                    assert match is not None
                    if match.team_all_forfeit(mine):
                        score = 'F'
                    else:
                        a_points, b_points = match.effective_game_points
                        is_a = match.stored_team_board.team_a_id == mine
                        mine_points = a_points if is_a else b_points
                        theirs_points = b_points if is_a else a_points
                        if mine_points > theirs_points:
                            score = '1'
                        elif mine_points < theirs_points:
                            score = '0'
                        else:
                            score = '½'
                cells[mine][theirs].append(GridEncounter(round_, score))
    return cells


@dataclass
class TeamPlayerRow:
    """A player in the grid of a team round robin detailed by player: their
    number, their team, whether they open its block of rows, and their
    points."""

    tournament_player: TournamentPlayer
    number: int
    team: Team
    first_of_team: bool
    points_str: str = ''


def team_player_grid(
    tournament: Tournament,
    teams: list[Team],
    shows_result: Callable[[int], bool],
) -> tuple[list[TeamPlayerRow], dict[int, dict[int, list[str]]]]:
    """The players of the team round robin *tournament*, team after team in
    the order of *teams*, and the results of their games against each other
    player, by player id and opponent id. Lineups change from round to
    round, so only the games played are known; a result is given when
    *shows_result* accepts its round. A player's points leave out their
    annulled games."""
    rows: list[TeamPlayerRow] = []
    for team in teams:
        first = True
        for player in team.players:
            tournament_player = tournament.tournament_players_by_id.get(player.id)
            if tournament_player is None:
                continue
            rows.append(TeamPlayerRow(tournament_player, len(rows) + 1, team, first))
            first = False
    player_ids = [row.tournament_player.id for row in rows]
    cells: dict[int, dict[int, list[str]]] = {
        player_id: {
            opponent_id: [] for opponent_id in player_ids if opponent_id != player_id
        }
        for player_id in player_ids
    }
    for row in rows:
        tournament_player = row.tournament_player
        points = 0.0
        for pairing in tournament_player.pairings.values():
            opponent_id = pairing.opponent_id
            if (
                not shows_result(pairing.round)
                or not opponent_id
                or opponent_id not in cells[tournament_player.id]
                or pairing.result == Result.NO_RESULT
            ):
                continue
            cells[tournament_player.id][opponent_id].append(
                pairing.result.to_berger_table
            )
            if not tournament_player.game_is_annulled(pairing):
                points += pairing.result.points(tournament.point_values)
        row.points_str = Utils.points_str(points)
    return rows, cells
