"""Tie-breaks specific to the French school competitions."""

from common.i18n import _
from data.tie_breaks.categories import TeamScoreCategory, TieBreakCategory
from data.tie_breaks.options import TieBreakOption
from data.tie_breaks.team_records import TeamRecord
from data.tie_breaks.team_tie_breaks import TeamTieBreak, TeamTieBreakContext
from plugins.fra_schools import PLUGIN_NAME


class BoardOrderWinsTieBreak(TeamTieBreak):
    """FFE school championship *nombre de gains au 1er échiquier, puis au
    2e, etc.* (J03 art. 5.3.3.b).

    Teams are compared on how many games they won on board 1; only if
    those are equal does board 2 decide, then board 3, and so on. That
    is a lexicographic comparison, but the standings machinery ranks on
    a single number — so the per-board win counts are packed into one
    positional value, board 1 taking the most significant place:

        Σ wins(board i) × (rounds + 1) ^ (boards - 1 - i)

    A base of ``rounds + 1`` leaves every count its own digit (a team
    can win a given board at most once per round), which makes the
    ordering of the packed value identical to the lexicographic one.
    Eight boards over nine rounds pack into 10^8 — far inside the range
    float64 represents exactly.

    A *gain* is a board on which the team scored the full point. Under
    the championship's own scoring (art. 5.3.1: a win 1, a draw noted X
    and worth 0, a loss 0) that is exactly its wins, and it stays exact
    under standard 1-½-0 scoring too.
    """

    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-BOARD-ORDER-WINS'

    @staticmethod
    def static_name() -> str:
        return _('Wins by board order')

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return []

    @property
    def base_acronym(self) -> str:
        return 'BOW'

    @property
    def trf_acronym(self) -> str:
        return 'OTHER_FRA_SCHOOLS_BOARD_ORDER_WINS'

    @property
    def is_fide(self) -> bool:
        return False

    @property
    def base_help_text(self) -> str:
        return _(
            'Compares the number of games won on board 1; if equal, on '
            'board 2, then board 3, and so on down the boards (French '
            'school championship, art. 5.3.3).'
        )

    @property
    def category(self) -> TieBreakCategory:
        return TeamScoreCategory()

    def compute_team_value(
        self,
        team_record: TeamRecord,
        all_records: dict[int, TeamRecord],
        tournament_context: TeamTieBreakContext,
        *,
        after_round: int,
    ) -> float:
        boards = tournament_context.team_player_count
        if boards <= 0:
            return 0.0
        wins_by_board = [0] * boards
        for match in team_record.matches:
            if match.round_ > after_round:
                continue
            for board_index, score in enumerate(match.board_scores):
                if board_index >= boards:
                    break
                if score >= 1.0:
                    wins_by_board[board_index] += 1
        base = max(tournament_context.rounds, 1) + 1
        total = 0.0
        for wins in wins_by_board:
            total = total * base + wins
        return total
