"""Advancement tie-break resolution for knock-out matches."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from data.pairings.knockout_helpers.common import (
    board_winner_player_id,
    loss_is_elimination,
    team_match_all_games_played,
    team_match_winner_id,
)
from utils.enum import Result

if TYPE_CHECKING:
    from data.board import Board
    from data.teams.team_board import TeamBoard
    from data.tie_breaks.team_records import TeamRecord
    from data.tie_breaks.team_tie_breaks import TeamTieBreakContext
    from data.tournament import Tournament


@dataclass(frozen=True)
class AdvancementValue:
    """One advancement tie-break's row in a level knock-out match."""

    acronym: str
    value_a: float | None
    value_b: float | None
    decisive: bool
    used: bool
    is_manual: bool = False
    # Whether the values are worth showing. A tie-break that compares board
    # by board packs the boards into one number to sort on, which reads as
    # an astronomical figure and tells the arbiter nothing.
    displayable: bool = True


@dataclass(frozen=True)
class KnockoutAdvancement:
    """Who advances from a level knock-out match, and why."""

    winner_id: int | None
    reason: str | None
    manual_pending: bool
    breakdown: tuple['AdvancementValue', ...] = ()
    manual_reached: bool = False


class KnockoutAdvancementMixin:
    """Resolve tied knock-out matches through configured advancement criteria."""

    def team_advancement(
        self, tournament: 'Tournament', team_board: 'TeamBoard'
    ) -> 'KnockoutAdvancement':
        stb = team_board.stored_team_board
        if stb.team_b_id is None:
            return KnockoutAdvancement(stb.team_a_id, None, False)
        round_ = team_board.round
        records: dict[int, TeamRecord] | None = None
        context: TeamTieBreakContext | None = None
        breakdown: list[AdvancementValue] = []
        winner_id: int | None = None
        reason: str | None = None
        manual_pending = False
        manual_reached = False
        decided = False
        for tie_break in tournament.advancement_tie_breaks:
            used = not decided
            if tie_break.is_manual:
                winner = stb.knockout_winner_team_id
                if used:
                    winner_id = winner
                    reason = tie_break.acronym if winner is not None else None
                    manual_pending = winner is None
                    manual_reached = True
                    decided = True
                breakdown.append(
                    AdvancementValue(
                        tie_break.acronym,
                        None,
                        None,
                        decisive=used and winner is not None,
                        used=used,
                        is_manual=True,
                    )
                )
                continue
            if not tie_break.supports_team_mode:
                continue
            if records is None:
                records = {
                    record.team_id: record
                    for record in tournament.team_records(after_round=round_)
                }
                context = tournament.team_tie_break_context()
            record_a = records.get(stb.team_a_id)
            record_b = records.get(stb.team_b_id)
            if record_a is None or record_b is None:
                continue
            assert context is not None
            value_a = float(
                tie_break.compute_team_value(
                    record_a, records, context, after_round=round_
                )
            )
            value_b = float(
                tie_break.compute_team_value(
                    record_b, records, context, after_round=round_
                )
            )
            decisive = used and value_a != value_b
            if decisive:
                winner_id = stb.team_a_id if value_a > value_b else stb.team_b_id
                reason = tie_break.acronym
                decided = True
            breakdown.append(
                AdvancementValue(
                    tie_break.acronym,
                    value_a,
                    value_b,
                    decisive,
                    used,
                    displayable=not tie_break.display_rank_delta,
                )
            )
        return KnockoutAdvancement(
            winner_id, reason, manual_pending, tuple(breakdown), manual_reached
        )

    def player_advancement(
        self, tournament: 'Tournament', board: 'Board'
    ) -> 'KnockoutAdvancement':
        player_a = board.optional_white_tournament_player
        player_b = board.black_tournament_player
        if player_a is None or player_b is None:
            return KnockoutAdvancement(None, None, False)
        round_ = board.round
        pairing_numbers_set = False
        breakdown: list[AdvancementValue] = []
        winner_id: int | None = None
        reason: str | None = None
        manual_pending = False
        manual_reached = False
        decided = False
        for tie_break in tournament.advancement_tie_breaks:
            used = not decided
            if tie_break.is_manual:
                winner = board.stored_board.knockout_winner_player_id
                if used:
                    winner_id = winner
                    reason = tie_break.acronym if winner is not None else None
                    manual_pending = winner is None
                    manual_reached = True
                    decided = True
                breakdown.append(
                    AdvancementValue(
                        tie_break.acronym,
                        None,
                        None,
                        decisive=used and winner is not None,
                        used=used,
                        is_manual=True,
                    )
                )
                continue
            if tie_break.is_team_tiebreak:
                continue
            if not pairing_numbers_set:
                tournament.set_tournament_players_pairing_numbers()
                pairing_numbers_set = True
            value_a = float(
                tie_break.compute_player_value(player_a, after_round=round_)
            )
            value_b = float(
                tie_break.compute_player_value(player_b, after_round=round_)
            )
            decisive = used and value_a != value_b
            if decisive:
                winner_id = player_a.id if value_a > value_b else player_b.id
                reason = tie_break.acronym
                decided = True
            breakdown.append(
                AdvancementValue(
                    tie_break.acronym,
                    value_a,
                    value_b,
                    decisive,
                    used,
                    displayable=not tie_break.display_rank_delta,
                )
            )
        return KnockoutAdvancement(
            winner_id, reason, manual_pending, tuple(breakdown), manual_reached
        )

    def board_advancement(
        self, tournament: 'Tournament', board: 'Board'
    ) -> 'KnockoutAdvancement | None':
        if (
            board.optional_white_tournament_player is None
            or board.black_tournament_player is None
        ):
            return None
        if board.result == Result.NO_RESULT or board.result.is_bye:
            return None
        if board_winner_player_id(board) is not None:
            return None
        return self.player_advancement(tournament, board)

    def team_board_advancement(
        self, tournament: 'Tournament', team_board: 'TeamBoard'
    ) -> 'KnockoutAdvancement | None':
        stb = team_board.stored_team_board
        if stb.team_b_id is None or not team_match_all_games_played(team_board):
            return None
        a_gp, b_gp = team_board.effective_game_points
        if a_gp != b_gp:
            return None
        return self.team_advancement(tournament, team_board)

    def board_loser_id(self, tournament: 'Tournament', board: 'Board') -> int | None:
        """The player this game knocks out of the bracket, or ``None`` while
        it is undecided. A team match eliminates as a whole, so the games
        inside one name nobody."""
        if tournament.pairing_system.paired_by_team:
            return None
        white = board.optional_white_tournament_player
        black = board.black_tournament_player
        if white is None or black is None:
            return None
        winner = board_winner_player_id(board)
        if winner is None and not board.no_result:
            winner = self.player_advancement(tournament, board).winner_id
        if winner is None or not loss_is_elimination(self, tournament, board):
            return None
        return black.id if winner == white.id else white.id

    def team_board_loser_id(
        self, tournament: 'Tournament', team_board: 'TeamBoard'
    ) -> int | None:
        """The team this match knocks out of the bracket, or ``None`` while it
        is undecided."""
        stb = team_board.stored_team_board
        if stb.team_b_id is None:
            return None
        winner = team_match_winner_id(tournament, team_board)
        if winner is None or not loss_is_elimination(self, tournament, team_board):
            return None
        return stb.team_b_id if winner == stb.team_a_id else stb.team_a_id

    def advancement_has_manual(self, tournament: 'Tournament') -> bool:
        return any(
            tie_break.is_manual for tie_break in tournament.advancement_tie_breaks
        )

    def unresolved_matches(
        self, tournament: 'Tournament', round_: int
    ) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        if tournament.pairing_system.paired_by_team:
            for team_board in tournament.get_round_team_boards(round_):
                stb = team_board.stored_team_board
                if stb.team_b_id is None or not team_match_all_games_played(team_board):
                    continue
                if team_match_winner_id(tournament, team_board) is not None:
                    continue
                team_a = tournament.event.teams_by_id.get(stb.team_a_id)
                team_b = tournament.event.teams_by_id.get(stb.team_b_id)
                matches.append(
                    {
                        'kind': 'team',
                        'id': team_board.id,
                        'a_id': stb.team_a_id,
                        'a_name': team_a.name if team_a else '',
                        'b_id': stb.team_b_id,
                        'b_name': team_b.name if team_b else '',
                        'winner_id': stb.knockout_winner_team_id,
                    }
                )
            return matches
        for board in tournament.get_round_boards(round_):
            white = board.optional_white_tournament_player
            black = board.black_tournament_player
            if white is None or black is None or board.no_result:
                continue
            if board_winner_player_id(board) is not None:
                continue
            if self.player_advancement(tournament, board).winner_id is not None:
                continue
            matches.append(
                {
                    'kind': 'player',
                    'id': board.id,
                    'a_id': white.id,
                    'a_name': white.full_name,
                    'b_id': black.id,
                    'b_name': black.full_name,
                    'winner_id': board.stored_board.knockout_winner_player_id,
                }
            )
        return matches
