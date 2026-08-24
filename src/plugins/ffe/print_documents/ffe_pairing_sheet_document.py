"""'Fiche d'appariement' for the FFE team cups.

One page per team: the team's identity, its roster and the per-round
match summary, laid out like the official FFE form. The Coupe
Jean-Claude Loubatière, the Coupe de la Parité and the Championnat
Féminin (N1F / N2F) all run 4-board matches scored the same way and use
the same form, so one document serves the three — only the competition
logo differs. Rosters vary in size (5 for the Loubatière and the
Championnat Féminin, 6 for the Parité); the sheet lists whatever the
team holds.

Only offered for team events that have a tournament using one of those
rule sets.
"""

from pathlib import Path
from typing import Any

from common import BASE_DIR
from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.print_documents import PrintOption
from data.print_documents.documents import PrintDocument
from data.rule_sets import RuleSet
from data.print_documents.options import (
    OptionalTeamsPrintOption,
    TournamentPrintOption,
)
from data.tournament import Tournament
from plugins.ffe import PLUGIN_DIR
from plugins.ffe.ffe_rule_sets import (
    ChampionnatFemininN1N2RuleSet,
    CoupeDeLaPariteRuleSet,
    CoupeJeanClaudeLoubatiereRuleSet,
)
from plugins.ffe.utils import FFEUtils
from utils.enum import Result
from utils.file import image_file_inline_url, ttf_file_inline_url

_PAIRING_SHEET_RULE_SET_IDS = frozenset(
    {
        CoupeJeanClaudeLoubatiereRuleSet.static_id(),
        CoupeDeLaPariteRuleSet.static_id(),
        ChampionnatFemininN1N2RuleSet.static_id(),
    }
)

# Per-player round results shown as 1 / 0 / X (draw); blank for anything else
# (unplayed, bye, no result).
_WIN_RESULTS = {Result.WIN, Result.FORFEIT_WIN, Result.UNRATED_WIN}
_DRAW_RESULTS = {Result.DRAW, Result.UNRATED_DRAW, Result.HALF_POINT_BYE}
_LOSS_RESULTS = {Result.LOSS, Result.FORFEIT_LOSS, Result.UNRATED_LOSS}


def _player_result_symbol(result: Result | None) -> str:
    if result in _WIN_RESULTS:
        return '1'
    if result in _DRAW_RESULTS:
        return 'X'
    if result in _LOSS_RESULTS:
        return '0'
    return ''


def _ordinal_fr(rank: int) -> str:
    return '1er' if rank == 1 else f'{rank}e'


_FONT_FILE = BASE_DIR / 'src/web/static/fonts/AtkinsonHyperlegibleNextVF-Variable.ttf'
_FFE_LOGO_FILE = PLUGIN_DIR / 'static/images/ffe-text.png'
_IMAGES_DIR = PLUGIN_DIR / 'static/images'


def _competition_logo_file(rule_set: RuleSet | None) -> Path | None:
    """The logo of the competition a tournament runs, or None when there
    is none to print.

    The Championnat Féminin covers both Nationale 1 and Nationale 2 but
    the artwork on file is the Nationale 2 one, so N1F prints without a
    logo rather than with the wrong division's.
    """
    match rule_set:
        case CoupeJeanClaudeLoubatiereRuleSet():
            return _IMAGES_DIR / 'loubatiere.svg'
        case CoupeDeLaPariteRuleSet():
            return _IMAGES_DIR / 'parite.jpg'
        case ChampionnatFemininN1N2RuleSet() if rule_set.is_nationale_2:
            return _IMAGES_DIR / 'championnat-feminin.jpg'
    return None


class FfePairingSheetDocument(PrintDocument):
    """One-page-per-team FFE *Fiche d'appariement*. Gated to team events
    with a tournament running one of the FFE team cups."""

    @staticmethod
    def static_id() -> str:
        return 'ffe-pairing-sheet'

    @staticmethod
    def static_name() -> str:
        return _('FFE pairing sheet')

    @property
    def title(self) -> str:
        return _('FFE pairing sheet')

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [TournamentPrintOption, OptionalTeamsPrintOption]

    @classmethod
    def is_available(cls, allowed_tournaments: list[Tournament]) -> bool:
        if not super().is_available(allowed_tournaments):
            return False
        return any(
            tournament.event.is_team_event
            and tournament.rule_set_id in _PAIRING_SHEET_RULE_SET_IDS
            for tournament in allowed_tournaments
        )

    @property
    def template_name(self) -> str:
        return '/print/ffe_pairing_sheet.html'

    def _team_round_colour(
        self, team: Any, round_: int, team_boards_by_round: dict[int, list[Any]]
    ) -> str:
        """'B' (Blanc) / 'N' (Noir) — the team's colour on its top board
        for the round, or '' when it can't be determined."""
        for team_board in team_boards_by_round.get(round_, []):
            stored = team_board.stored_team_board
            if team.id not in (stored.team_a_id, stored.team_b_id):
                continue
            for board in sorted(
                team_board.boards, key=lambda b: (b.index is None, b.index or 0)
            ):
                white_team_id, _black = team_board.board_team_ids(board)
                if white_team_id is not None:
                    return 'B' if white_team_id == team.id else 'N'
        return ''

    def _team_context(
        self,
        team: Any,
        letter: str,
        rounds: list[int],
        records_by_id: dict[int, Any],
        team_boards_by_round: dict[int, list[Any]],
        rank_by_team_id: dict[int, int],
        team_count: int,
    ) -> dict[str, Any]:
        event = self.get_event()
        tournament = self.tournament
        record = records_by_id.get(team.id)
        rounds_context: list[dict[str, Any]] = []
        cumulative_match_points = 0.0
        total_differential = 0.0
        total_gains = 0.0
        has_results = False
        for round_ in rounds:
            colour = self._team_round_colour(team, round_, team_boards_by_round)
            match = record.match_at(round_) if record else None
            if match is None:
                # An unplayed round still needs the full shape so the
                # template's `is not none` guards don't trip on a missing key.
                rounds_context.append(
                    {
                        'round': round_,
                        'colour': colour,
                        'opponent': '',
                        'gains': None,
                        'differential': None,
                        'match_points': None,
                        'total_match_points': None,
                    }
                )
                continue
            has_results = True
            opponent = (
                event.teams_by_id.get(match.opponent_id)
                if match.opponent_id is not None
                else None
            )
            opponent_match = None
            if match.opponent_id is not None:
                opponent_record = records_by_id.get(match.opponent_id)
                opponent_match = (
                    opponent_record.match_at(round_) if opponent_record else None
                )
            # Points pour / contre are each floored at 0 per match (a forfeit
            # can drive a raw match total negative), matching the FFE GP-FOR /
            # GP-DIFFERENTIAL tie-breaks — so the sheet agrees with them.
            gains = max(0.0, match.own_gp)
            against = max(0.0, opponent_match.own_gp) if opponent_match else None
            differential = gains - against if against is not None else None
            if differential is not None:
                total_differential += differential
            total_gains += gains
            cumulative_match_points += match.own_mp
            rounds_context.append(
                {
                    'round': round_,
                    'colour': colour,
                    'opponent': opponent.name
                    if opponent
                    else (_('Bye') if match.is_bye else ''),
                    'gains': gains,
                    'differential': differential,
                    'match_points': match.own_mp,
                    'total_match_points': cumulative_match_points,
                }
            )
        players_context = []
        for index, player in enumerate(team.players, start=1):
            tournament_player = tournament.tournament_players_by_id.get(player.id)
            results = {}
            if tournament_player is not None:
                for round_ in rounds:
                    pairing = tournament_player.pairings_by_round.get(round_)
                    results[round_] = (
                        _player_result_symbol(pairing.result) if pairing else ''
                    )
            players_context.append(
                {
                    'number': index,
                    'name': player.full_name,
                    'code_ffe': FFEUtils.get_player_plugin_data(
                        player
                    ).ffe_licence_number
                    or '',
                    'elo': player.event_default_rating,
                    'results': results,
                }
            )
        rank = rank_by_team_id.get(team.id)
        return {
            'letter': letter,
            'name': team.name,
            'captain': team.captain_display_name or '',
            'federation': team.federation,
            'group': team.group.name if team.group else '',
            'average_elo': team.lineup_average_rating(1) or team.average_rating,
            'players': players_context,
            'rounds': rounds_context,
            'total_match_points': record.total_mp if (record and has_results) else None,
            'total_gains': total_gains if has_results else None,
            'total_differential': total_differential if has_results else None,
            'classement': f'{_ordinal_fr(rank)} / {team_count}' if rank else '',
        }

    def _competition_logo_url(self) -> str | None:
        logo_file = _competition_logo_file(self.tournament.rule_set)
        # Rendered only when the file is there, so a competition whose
        # logo hasn't been added yet still prints — just without it.
        if logo_file is None or not logo_file.is_file():
            return None
        return image_file_inline_url(logo_file)

    @property
    def template_context(self) -> dict[str, Any]:
        tournament = self.tournament
        rounds = list(range(1, tournament.rounds + 1))
        all_teams = sorted(
            tournament.teams,
            key=lambda team: (
                team.pairing_number
                if team.pairing_number is not None
                else float('inf'),
                team.name.lower(),
            ),
        )
        # Letters and team count reflect the whole tournament (the table
        # position), even when only some teams are printed.
        letter_by_id = {
            team.id: chr(ord('A') + index) for index, team in enumerate(all_teams)
        }
        team_count = len(all_teams)
        # The arbiter may pick which teams to print; empty selection = all.
        selected_team_ids = set(self._get_option(OptionalTeamsPrintOption).value or [])
        teams = [
            team
            for team in all_teams
            if not selected_team_ids or team.id in selected_team_ids
        ]
        records_by_id = {record.team_id: record for record in tournament.team_records()}
        team_boards_by_round = tournament.team_boards_by_round
        rank_by_team_id = {
            row['team'].id: row['rank'] for row in tournament.team_standings()
        }
        return {
            'sharly_chess_config': SharlyChessConfig(),
            'document': self,
            'font_family': _FONT_FILE.stem,
            'font_url': ttf_file_inline_url(_FONT_FILE),
            'ffe_logo_url': image_file_inline_url(_FFE_LOGO_FILE),
            'competition_logo_url': self._competition_logo_url(),
            'competition_name': rule_set.name
            if (rule_set := tournament.rule_set)
            else '',
            'tournament': tournament,
            'rounds': rounds,
            'teams': [
                self._team_context(
                    team,
                    letter_by_id[team.id],
                    rounds,
                    records_by_id,
                    team_boards_by_round,
                    rank_by_team_id,
                    team_count,
                )
                for team in teams
            ],
        }
