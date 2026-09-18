"""Common result helpers for knock-out pairing engines."""

from typing import TYPE_CHECKING, Any

from common.i18n import _, pgettext
from utils.enum import Result

if TYPE_CHECKING:
    from data.board import Board
    from data.player import TournamentPlayer
    from data.teams.team_board import TeamBoard
    from data.tournament import Tournament


def seeded_players(tournament: 'Tournament') -> dict[int, 'TournamentPlayer']:
    """The field in seed order, by seed. The pairing numbers hold that order:
    they are the starting order as it stood when the bracket was drawn, and
    the starting order itself until then. Reading the starting rank instead
    would re-seed the bracket under a rating corrected mid-event."""
    return tournament.tournament_players_by_pairing_number


def seed_sort_key(player: 'TournamentPlayer') -> tuple:
    """Where a player sits in the seed order. A team's players are
    synthesised from its roster and hold no pairing number; they fall back to
    the starting rank, which is all they have."""
    if player.pairing_number is not None:
        return (0, player.pairing_number)
    return (1, *player.starting_rank_sort_key)


def loss_is_elimination(engine: Any, tournament: 'Tournament', board: Any) -> bool:
    """Whether losing this match puts its loser out of the tournament. It does
    in a single elimination, where one loss is the whole story; a double
    elimination seats a first-time loser in its other bracket and says so
    itself."""
    stays = getattr(engine, 'loser_stays_in_bracket', None)
    return not stays(tournament, board) if stays is not None else True


def tie_resolution_message(tournament: 'Tournament', round_: int) -> str:
    """Why a round blocks the next knock-out pairing."""
    if tournament.knockout.advancement_has_manual:
        return _(
            'Resolve the tied match(es) of round {round} before pairing the next round.'
        ).format(round=round_)
    return (
        pgettext(
            'team knock-out',
            'Round {round} has tied match(es) that the advancement tie-breaks '
            'cannot decide. Add the "Manual" tie-break in the tie-break settings '
            'to designate the winner of a play-off — or add other advancement '
            'tie-breaks.',
        ).format(round=round_)
        if tournament.is_team_tournament
        else pgettext(
            'individual knock-out',
            'Round {round} has tied match(es) that the advancement tie-breaks '
            'cannot decide. Add the "Manual" tie-break in the tie-break settings '
            'to designate the winner of a play-off — or add other advancement '
            'tie-breaks.',
        ).format(round=round_)
    )


def board_winner_player_id(board: 'Board') -> int | None:
    """The player who advances from *board*, or ``None`` if undecided."""
    white = board.optional_white_tournament_player
    black = board.black_tournament_player
    if black is None:
        return white.id if white is not None else None
    if white is None:
        return black.id
    result = board.result
    if result == Result.NO_RESULT or result.is_bye:
        return None
    white_points = result.point_value
    black_points = result.opposite_result.point_value
    if white_points > black_points:
        return white.id
    if black_points > white_points:
        return black.id
    return None


def team_match_all_games_played(team_board: 'TeamBoard') -> bool:
    """Whether every game of a team match has been played. A board with
    neither seat filled is a slot the teams left empty: it carries no result
    and never will, so the match is not waiting on it."""
    return not any(
        board.no_result
        for board in team_board.boards
        if board.optional_white_tournament_player is not None
        or board.black_tournament_player is not None
    )


def team_match_winner_id(
    tournament: 'Tournament', team_board: 'TeamBoard'
) -> int | None:
    """The team that advances from *team_board*, or ``None`` if undecided."""
    stb = team_board.stored_team_board
    if stb.team_b_id is None:
        return stb.team_a_id
    if not team_match_all_games_played(team_board):
        # A match with a game still to play is undecided, whoever leads: the
        # games left can level it, and a lineup change that clears a board
        # puts a decided match back in play.
        return None
    a_gp, b_gp = team_board.effective_game_points
    if a_gp > b_gp:
        return stb.team_a_id
    if b_gp > a_gp:
        return stb.team_b_id
    return tournament.knockout.advancement_winner(team_board)


def find_knockout_board(
    tournament: 'Tournament', round_: int, a_id: int | None, b_id: int
) -> 'Board | None':
    """Find a knock-out board by its expected players.

    Prefer the exact pair, but fall back to whichever expected player is present
    so already-paired later rounds survive an edited earlier result.
    """
    wanted = {a_id, b_id}
    best: Board | None = None
    best_overlap = 0
    for board in tournament.get_round_boards(round_):
        white = board.optional_white_tournament_player
        black = board.black_tournament_player
        if black is None:
            continue
        seated = {p.id for p in (white, black) if p is not None}
        overlap = len(seated & wanted)
        if overlap > best_overlap:
            best, best_overlap = board, overlap
            if overlap == 2:
                break
    return best


def find_knockout_team_board(
    tournament: 'Tournament', round_: int, a_id: int | None, b_id: int
) -> 'TeamBoard | None':
    """Find a knock-out team board by its expected teams."""
    wanted = {a_id, b_id}
    best: TeamBoard | None = None
    best_overlap = 0
    for team_board in tournament.team_boards_by_round.get(round_, []):
        stb = team_board.stored_team_board
        if stb.team_b_id is None:
            continue
        overlap = len({stb.team_a_id, stb.team_b_id} & wanted)
        if overlap > best_overlap:
            best, best_overlap = team_board, overlap
            if overlap == 2:
                break
    return best
