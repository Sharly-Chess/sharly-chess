"""The FFE *Championnat de France Interclubs Jeunes* (J02): team matches
whose last boards, held by the youngest players, play a second game in the
same match, each of their games being worth half a game of the other
boards.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, cast, override

from common.i18n import _, ngettext
from data.player_categories import JuniorCategory
from data.rule_sets.rule_sets import PointAdjustment, RuleSetField
from data.teams.extra_game import ExtraGameSeat
from plugins.ffe.ffe_entity import FfeLicenceTournamentCriterion
from plugins.ffe.ffe_rule_sets import (
    FfeTeamCompetitionRuleSet,
    _FfeTeamCupRuleSet,
    _fmt,
)
from plugins.ffe.utils import PlayerFFELicence
from utils.enum import Cadence, Result, ScoreType, TeamColourType

if TYPE_CHECKING:
    from data.board import Board
    from data.player import Player
    from data.teams.team import Team
    from data.teams.team_board import TeamBoard
    from database.sqlite.event.event_store import StoredTournament

# Art. 4.2: a match won scores 3, drawn 2, lost over the board 1, lost by
# forfeit 0, and "une équipe bénéficiant d'une exemption ne marque aucun
# point".
_MATCH_POINTS: dict[int, float] = {
    Result.WIN.value: 3.0,
    Result.DRAW.value: 2.0,
    Result.LOSS.value: 1.0,
    Result.ZERO_POINT_BYE.value: 0.0,
    Result.PAIRING_ALLOCATED_BYE.value: 0.0,
}

# Art. 4.1, on the boards that play one game: a game won scores 2, and a
# draw is noted X and "n'est pas comptabilisée dans le score final". A game
# of a board that plays two is worth half: 1 when won.
_GAME_POINTS: dict[int, float] = {
    Result.WIN.value: 2.0,
    Result.DRAW.value: 0.0,
    Result.LOSS.value: 0.0,
    Result.ZERO_POINT_BYE.value: 0.0,
    Result.PAIRING_ALLOCATED_BYE.value: 0.0,
}

# Art. 4.4: match points, the results between the tied teams, the
# differential, the points scored, then the differentials board by board.
_TIE_BREAKS: list[tuple[str, dict]] = [
    ('POINTS', {}),
    ('ffe-MUTUAL-RESULTS', {}),
    ('ffe-GP-DIFFERENTIAL', {}),
    ('ffe-GP-FOR', {}),
    ('ffe-BOARD-DIFFERENTIAL', {}),
]

_DIVISION_TOP_JEUNES = 'top-jeunes'
_DIVISION_NATIONALE_1 = 'nationale-1'
_DIVISION_NATIONALE_2 = 'nationale-2'

_SECOND_GAMES_NONE = 'none'
_SECOND_GAMES_LAST_BOARD = 'last-board'
_SECOND_GAMES_LAST_TWO_BOARDS = 'last-two-boards'

_SECOND_GAME_COUNTS = {
    _SECOND_GAMES_NONE: 0,
    _SECOND_GAMES_LAST_BOARD: 1,
    _SECOND_GAMES_LAST_TWO_BOARDS: 2,
}


def _division_choices() -> tuple[tuple[str, str], ...]:
    """Built on each call: ``_()`` translates eagerly, so a module-level
    tuple would freeze the labels in the locale of the first import."""
    return (
        (_DIVISION_TOP_JEUNES, _('Top Jeunes')),
        (_DIVISION_NATIONALE_1, _('Nationale 1')),
        (_DIVISION_NATIONALE_2, _('Nationale 2')),
    )


def _second_games_choices() -> tuple[tuple[str, str], ...]:
    """Built on each call — see :func:`_division_choices`."""
    return (
        (_SECOND_GAMES_LAST_BOARD, _('The last board')),
        (_SECOND_GAMES_LAST_TWO_BOARDS, _('The last two boards')),
        (_SECOND_GAMES_NONE, _('No board')),
    )


def _alternating_colours(board_count: int) -> str:
    """Art. 3.2: the first-named team has white on the odd boards and black
    on the even ones."""
    return ''.join('W' if index % 2 == 0 else 'B' for index in range(board_count))


class _InterclubsJeunesRuleSet(FfeTeamCompetitionRuleSet, ABC):
    """What the divisions of the championship share: the last boards of a
    match play a second game, and the line-up goes by age."""

    STANDARD_BOARD_COUNT: int
    STANDARD_SECOND_GAME_COUNT: int
    STANDARD_AGE_LIMITS: tuple[int, ...]

    @property
    @abstractmethod
    def second_game_count(self) -> int:
        """How many of the last boards play a second game."""

    def second_game_boards(self, board_count: int) -> tuple[int, ...]:
        """The indexes of the boards that play a second game, among
        ``board_count``."""
        count = min(self.second_game_count, board_count)
        return tuple(range(board_count - count, board_count))

    def board_age_limits(self, board_count: int) -> tuple[int, ...] | None:
        """The age category the player of each board may not exceed, for
        the boards the regulations describe; ``None`` for any other
        format, which a league sets with the federation."""
        if (
            board_count != self.STANDARD_BOARD_COUNT
            or self.second_game_count != self.STANDARD_SECOND_GAME_COUNT
        ):
            return None
        return self.STANDARD_AGE_LIMITS

    def colour_pattern(self, board_count: int) -> str:
        """The colour of the first-named team on each board, in the first
        game of those that play two."""
        return _alternating_colours(board_count)

    @property
    @override
    def forbids_exports(self) -> bool:
        return True

    @property
    @override
    def locked_once_paired(self) -> bool:
        return True

    @override
    def rounds_for_pairing(
        self,
        pairing_system_id: str,
        pairing_variation_id: str | None = None,
    ) -> int | None:
        if pairing_system_id == 'TEAM_ROUND_ROBIN':
            return 0
        return None

    @property
    @override
    def tie_break_overrides_by_pairing(self) -> dict[str, list[tuple[str, dict]]]:
        return {'TEAM_ROUND_ROBIN': _TIE_BREAKS, 'TEAM_SWISS': _TIE_BREAKS}

    @override
    def board_game_points(
        self,
        board_index: int,
        board_count: int,
        team_game_points: dict[Result, float],
    ) -> dict[Result, float]:
        if board_index not in self.second_game_boards(board_count):
            return team_game_points
        return {result: points / 2 for result, points in team_game_points.items()}

    @staticmethod
    def _board_count(team_board: TeamBoard) -> int:
        return team_board.tournament.team_player_count or len(team_board.boards)

    @override
    def extra_game_seats(self, team_board: TeamBoard) -> list[ExtraGameSeat]:
        """Art. 3.7.b and 3.2: each of the last boards plays a second game
        with the colours reversed, against the same opponent with one such
        board, against the opponent of the other one with two."""
        boards = {board.index: board for board in team_board.boards}
        board_count = self._board_count(team_board)
        indexes = self.second_game_boards(board_count)
        if any(index not in boards for index in indexes):
            return []
        opposite = dict(zip(indexes, reversed(indexes), strict=True))
        seats = []
        for index in indexes:
            team_a_player_id, _team_b_player_id, team_a_was_white = self._sides(
                team_board, boards[index], board_count
            )
            _team_a_player_id, team_b_player_id, _was_white = self._sides(
                team_board, boards[opposite[index]], board_count
            )
            if team_a_was_white:
                white_player_id, black_player_id = team_b_player_id, team_a_player_id
                white_board_index, black_board_index = opposite[index], index
            else:
                white_player_id, black_player_id = team_a_player_id, team_b_player_id
                white_board_index, black_board_index = index, opposite[index]
            seats.append(
                ExtraGameSeat(
                    key=f'{index + 1}-{opposite[index] + 1}',
                    label=_('{board}b').format(board=index + 1),
                    description=_('Board {board}, second game').format(board=index + 1),
                    white_board_index=white_board_index,
                    black_board_index=black_board_index,
                    white_player_id=white_player_id,
                    black_player_id=black_player_id,
                )
            )
        return seats

    def _sides(
        self, team_board: TeamBoard, board: Board, board_count: int
    ) -> tuple[int | None, int | None, bool]:
        """The players of team A and of team B on ``board``, and whether
        team A has white there: from the players seated, and from the
        colours of the regulations when both sides are empty."""
        white_team_id, black_team_id = team_board.board_team_ids(board)
        if white_team_id is None and black_team_id is None:
            team_a_is_white = self.colour_pattern(board_count)[board.index] == 'W'
        else:
            team_a_is_white = white_team_id == team_board.stored_team_board.team_a_id
        if team_a_is_white:
            return board.white_player_id, board.black_player_id, True
        return board.black_player_id, board.white_player_id, False

    def forfeit_win_score(self, board_count: int) -> float | None:
        """Art. 3.8: what a team scores for a match its opponent forfeited,
        on the boards the regulations describe; ``None`` for any other
        format, whose regulations are the league's."""
        return None

    def forfeit_limit(self, board_count: int) -> int | None:
        """Art. 3.8: how many of its players a team may forfeit without
        forfeiting the match, on the boards the regulations describe;
        ``None`` for any other format, whose regulations are the league's."""
        return None

    @override
    def team_point_adjustment(self, team: Team, round_: int) -> PointAdjustment | None:
        team_board = _FfeTeamCupRuleSet._team_round_match(team, round_)
        if team_board is None:
            return None
        forfeiting_team_ids = self._teams_forfeiting_match(team_board)
        if forfeiting_team_ids:
            return self._forfeited_match_adjustment(
                team, team_board, forfeiting_team_ids
            )
        stored_team_board = team_board.stored_team_board
        is_team_a = stored_team_board.team_a_id == team.id
        opponent_id = (
            stored_team_board.team_b_id if is_team_a else stored_team_board.team_a_id
        )
        if opponent_id is None:
            return None
        first_empty_board = self._first_empty_board(team_board, team.id)
        opponent_first_empty_board = self._first_empty_board(team_board, opponent_id)
        vacancy_gp = self._vacancy_game_points(team_board)[0 if is_team_a else 1]
        scored = team_board.game_points[0 if is_team_a else 1] + vacancy_gp
        explanations = []
        if first_empty_board is not None and vacancy_gp:
            explanations.append(
                _(
                    'No player on board {board}: that board and the following '
                    'ones are lost by forfeit.'
                ).format(board=first_empty_board + 1)
            )
        if opponent_first_empty_board is not None and vacancy_gp:
            explanations.append(
                _(
                    'The opponent has no player on board {board}: that board '
                    'and the following ones are won by forfeit.'
                ).format(board=opponent_first_empty_board + 1)
            )
        penalty = self._forfeit_penalty(team, team_board, scored, first_empty_board)
        if penalty is not None:
            explanations.append(penalty.explanation)
        if not explanations:
            return None
        return PointAdjustment(
            gp=vacancy_gp + (penalty.gp if penalty else 0.0),
            explanation=' '.join(explanations),
        )

    def _first_empty_board(self, team_board: TeamBoard, team_id: int) -> int | None:
        """The index of the first board on which *team_id* has no player."""
        board_count = self._board_count(team_board)
        is_team_a = team_board.stored_team_board.team_a_id == team_id
        for board in sorted(team_board.boards, key=lambda board: board.index):
            team_a_player_id, team_b_player_id, _team_a_is_white = self._sides(
                team_board, board, board_count
            )
            if (team_a_player_id if is_team_a else team_b_player_id) is None:
                return board.index
        return None

    @override
    def administrative_forfeits(self, team_board: TeamBoard) -> dict[int, int]:
        stored_team_board = team_board.stored_team_board
        if stored_team_board.team_b_id is None:
            return {}
        return {
            team_id: first_empty_board
            for team_id in (stored_team_board.team_a_id, stored_team_board.team_b_id)
            if (first_empty_board := self._first_empty_board(team_board, team_id))
            is not None
        }

    def _vacancy_game_points(self, team_board: TeamBoard) -> tuple[float, float]:
        """Art. 3.6: the line-up "ne peut comporter de trou : s'il n'y a pas
        de nom écrit à un certain échiquier, l'échiquier vacant et les
        suivants sont automatiquement perdus par forfait administratif",
        such a game being "comptée 0 point, et gagnée par l'adversaire"
        (art. 4.1). The games keep the result they were played to, which
        the rating counts (art. 3.1): what is returned is the difference
        this makes to the game points of team A and of team B."""
        stored_team_board = team_board.stored_team_board
        team_a_id, team_b_id = stored_team_board.team_a_id, stored_team_board.team_b_id
        if team_b_id is None:
            return 0.0, 0.0
        board_count = self._board_count(team_board)
        first_empty_a = self._first_empty_board(team_board, team_a_id)
        first_empty_b = self._first_empty_board(team_board, team_b_id)

        def difference(
            index_a: int, index_b: int, points_a: float, points_b: float
        ) -> tuple[float, float]:
            lost_by_a = first_empty_a is not None and index_a >= first_empty_a
            lost_by_b = first_empty_b is not None and index_b >= first_empty_b
            if not lost_by_a and not lost_by_b:
                return 0.0, 0.0
            wanted_a = (
                0.0
                if lost_by_a
                else Result.WIN.points(team_board.board_game_points(index_a))
            )
            wanted_b = (
                0.0
                if lost_by_b
                else Result.WIN.points(team_board.board_game_points(index_b))
            )
            return wanted_a - points_a, wanted_b - points_b

        total_a, total_b = 0.0, 0.0
        for board in team_board.boards:
            _a_id, _b_id, team_a_is_white = self._sides(team_board, board, board_count)
            game_points = team_board.board_game_points(board.index)
            white_pairing = board.optional_white_pairing
            white_points = (
                white_pairing.result.points(game_points) if white_pairing else 0.0
            )
            black_points = (
                board.black_pairing.result.points(game_points)
                if board.black_tournament_player
                else 0.0
            )
            points_a, points_b = (
                (white_points, black_points)
                if team_a_is_white
                else (black_points, white_points)
            )
            delta_a, delta_b = difference(board.index, board.index, points_a, points_b)
            total_a += delta_a
            total_b += delta_b
        for extra_game in team_board.extra_games:
            index_a = extra_game.board_index_of(team_a_id)
            index_b = extra_game.board_index_of(team_b_id)
            if index_a is None or index_b is None:
                continue
            delta_a, delta_b = difference(
                index_a,
                index_b,
                extra_game.team_points(team_a_id),
                extra_game.team_points(team_b_id),
            )
            total_a += delta_a
            total_b += delta_b
        return total_a, total_b

    def _teams_forfeiting_match(self, team_board: TeamBoard) -> set[int]:
        """Art. 3.8: "une équipe ayant plus de trois membres forfaits (1 en
        Nationale 3) perd le match"."""
        limit = self.forfeit_limit(self._board_count(team_board))
        stored_team_board = team_board.stored_team_board
        if limit is None or stored_team_board.team_b_id is None:
            return set()
        return {
            team_id
            for team_id in (stored_team_board.team_a_id, stored_team_board.team_b_id)
            if sum(
                1
                for _index, forfeited, _played in (
                    _FfeTeamCupRuleSet._team_board_breakdown(team_board, team_id)
                )
                if forfeited
            )
            > limit
        }

    def _forfeited_match_adjustment(
        self, team: Team, team_board: TeamBoard, forfeiting_team_ids: set[int]
    ) -> PointAdjustment | None:
        """Art. 3.8: a team that forfeits a match "perd le match sur le
        score de 3-0 (10-0 de points de parties, 5-0 en Nationale 3)". The
        games played beside the forfeits cannot add up to more, so that
        score stands whatever the boards hold, and the forfeiting team
        takes the match points of an absent team, not those of a match
        lost over the board."""
        board_count = self._board_count(team_board)
        score = self.forfeit_win_score(board_count)
        limit = self.forfeit_limit(board_count)
        if score is None or limit is None:
            return None
        stored_team_board = team_board.stored_team_board
        team_a_id = stored_team_board.team_a_id
        team_b_id = stored_team_board.team_b_id

        def target(team_id: int | None) -> float:
            opponent_id = team_b_id if team_id == team_a_id else team_a_id
            if team_id in forfeiting_team_ids or opponent_id not in forfeiting_team_ids:
                return 0.0
            return score

        targets = target(team_a_id), target(team_b_id)
        scored_pair = team_board.game_points
        is_team_a = team_a_id == team.id
        scored = scored_pair[0] if is_team_a else scored_pair[1]
        wanted = targets[0] if is_team_a else targets[1]
        mp = 0.0
        if team.id in forfeiting_team_ids:
            match_points = team_board.match_points_pair(game_points=targets)
            assert match_points is not None
            tournament_match_points = team_board.tournament.match_points
            absent = tournament_match_points.get(
                Result.ZERO_POINT_BYE,
                tournament_match_points.get(Result.LOSS, 0.0),
            )
            mp = absent - (match_points[0] if is_team_a else match_points[1])
            explanation = ngettext(
                'More than {n} forfeited board: the match is lost by forfeit.',
                'More than {n} forfeited boards: the match is lost by forfeit.',
                limit,
            ).format(n=limit)
        else:
            explanation = _('Match won by forfeit, counted as {score}-0.').format(
                score=_fmt(score)
            )
        if not mp and wanted == scored:
            return None
        return PointAdjustment(mp=mp, gp=wanted - scored, explanation=explanation)

    def _forfeit_penalty(
        self,
        team: Team,
        team_board: TeamBoard,
        scored: float,
        first_empty_board: int | None,
    ) -> PointAdjustment | None:
        """Art. 4.1: a game lost by sporting forfeit on a board that plays
        one game counts as a game won taken away (-2) when a game was
        played on a following board. *scored* is what the team has on the
        boards; the boards from *first_empty_board* on are lost by
        administrative forfeit, which counts 0."""
        board_count = self._board_count(team_board)
        second_game_boards = self.second_game_boards(board_count)
        rows = [
            row
            for row in _FfeTeamCupRuleSet._team_board_breakdown(team_board, team.id)
            if first_empty_board is None or row[0] < first_empty_board
        ]
        played_indexes = [index for index, _forfeited, played in rows if played]
        if any(
            extra_game.played
            and (
                first_empty_board is None
                or (extra_game.board_index_of(team.id) or 0) < first_empty_board
            )
            for extra_game in team_board.extra_games
        ):
            played_indexes.append(board_count)
        if not played_indexes:
            return None
        last_played = max(played_indexes)
        count = sum(
            1
            for index, forfeited, _played in rows
            if forfeited and index < last_played and index not in second_game_boards
        )
        penalty = Result.WIN.points(team_board.tournament.team_game_points)
        if not count or not penalty:
            return None
        explanation = ngettext(
            '{n} forfeited board above a board on which a game was '
            'played, counted as -{points}.',
            '{n} forfeited boards above a board on which a game was '
            'played, counted as -{points} each.',
            count,
        ).format(n=count, points=_fmt(penalty))
        # Art. 4.1: "le score d'une équipe en points de parties [...] ne peut
        # être inférieur à zéro". Stopping the penalty at what the team
        # scored covers the result of the match as well as the standings,
        # both of which add it to the score of the boards.
        total = penalty * count
        if total > scored:
            total = max(scored, 0.0)
            explanation += ' ' + _('The match score cannot go below zero.')
        return PointAdjustment(gp=-total, explanation=explanation)

    @override
    def roster_warnings(self, team: Team) -> list[str]:
        tournament = team.tournament
        if tournament is None or not tournament.team_player_count:
            return []
        board_count = tournament.team_player_count
        lineup = team.effective_round_slots(max(tournament.current_round, 1))
        return [
            *self._age_category_warnings(lineup, self.board_age_limits(board_count)),
            *self._board_order_warnings(lineup, self.second_game_boards(board_count)),
        ]

    @staticmethod
    def _age_category_warnings(
        lineup: list[Player | None], age_limits: tuple[int, ...] | None
    ) -> list[str]:
        """Art. 3.7.b: each board is held by a player of its age category
        or younger."""
        msgs = []
        for index, (player, age_limit) in enumerate(
            zip(lineup, age_limits or (), strict=False)
        ):
            if player is None:
                continue
            category = player.category
            if isinstance(category, JuniorCategory) and category.age_limit <= age_limit:
                continue
            msgs.append(
                _(
                    'Board {board} is for a player of the U{age_limit} category '
                    'or younger: {name} ({category}).'
                ).format(
                    board=index + 1,
                    age_limit=age_limit,
                    name=player.full_name,
                    category=category.name or _('unknown'),
                )
            )
        return msgs

    @classmethod
    def _board_order_warnings(
        cls, lineup: list[Player | None], second_game_boards: tuple[int, ...]
    ) -> list[str]:
        """Art. 3.7.c: the boards go from the oldest player to the youngest,
        a player sitting above an older one only with a rating at least as
        high. The boards that play twice may sit either way round."""
        msgs = []
        for index, player in enumerate(lineup):
            if player is None:
                continue
            for lower_index in range(index + 1, len(lineup)):
                older = lineup[lower_index]
                if older is None or not cls._is_older(older, player):
                    continue
                if index in second_game_boards and lower_index in second_game_boards:
                    continue
                if (player.event_default_rating or 0) >= (
                    older.event_default_rating or 0
                ):
                    continue
                msgs.append(
                    _(
                        '{name} (board {board}) is younger than {older_name} '
                        '(board {older_board}) and has a lower rating: the '
                        'older player sits above.'
                    ).format(
                        name=player.full_name,
                        board=index + 1,
                        older_name=older.full_name,
                        older_board=lower_index + 1,
                    )
                )
        return msgs

    @staticmethod
    def _is_older(player: Player, other: Player) -> bool:
        if player.date_of_birth and other.date_of_birth:
            return player.date_of_birth < other.date_of_birth
        if player.year_of_birth and other.year_of_birth:
            return player.year_of_birth < other.year_of_birth
        return False

    def _standard_values(self) -> dict[str, str]:
        """The format and the scoring of the regulations, as the tournament
        form holds them."""
        return {
            'cadence': str(Cadence.STANDARD.value),
            'team_player_count': str(self.STANDARD_BOARD_COUNT),
            'color_pattern': self.colour_pattern(self.STANDARD_BOARD_COUNT),
            'primary_score': ScoreType.MATCH_POINTS.value,
            'mp_win': _fmt(_MATCH_POINTS[Result.WIN.value]),
            'mp_draw': _fmt(_MATCH_POINTS[Result.DRAW.value]),
            'mp_loss': _fmt(_MATCH_POINTS[Result.LOSS.value]),
            'mp_zpb': _fmt(_MATCH_POINTS[Result.ZERO_POINT_BYE.value]),
            'mp_pab': _fmt(_MATCH_POINTS[Result.PAIRING_ALLOCATED_BYE.value]),
            'gp_win': _fmt(_GAME_POINTS[Result.WIN.value]),
            'gp_draw': _fmt(_GAME_POINTS[Result.DRAW.value]),
            'gp_loss': _fmt(_GAME_POINTS[Result.LOSS.value]),
            'gp_zpb': _fmt(_GAME_POINTS[Result.ZERO_POINT_BYE.value]),
            'gp_pab': _fmt(_GAME_POINTS[Result.PAIRING_ALLOCATED_BYE.value]),
        }

    def _shared_values(
        self, pairing_system_id: str | None, pairing_variation_id: str | None
    ) -> dict[str, str]:
        """What every division imposes, as the tournament form holds it."""
        values = {
            FfeLicenceTournamentCriterion().form_key: PlayerFFELicence.A.value,
            'team_colour_type': TeamColourType.A.value,
            'secondary_score_for_colours': 'on',
        }
        if pairing_system_id is not None:
            rounds = self.rounds_for_pairing(pairing_system_id, pairing_variation_id)
            if rounds is not None:
                values['rounds'] = str(rounds) if rounds else ''
        return values

    def _apply_shared_defaults(
        self, stored_tournament: StoredTournament, pairing_system_id: str | None
    ) -> None:
        stored_tournament.criteria[FfeLicenceTournamentCriterion.static_id()] = (
            PlayerFFELicence.A.value
        )
        stored_tournament.team_colour_type = TeamColourType.A.value
        stored_tournament.secondary_score_for_colours = True
        if pairing_system_id is not None:
            rounds = self.rounds_for_pairing(
                pairing_system_id, stored_tournament.pairing
            )
            if rounds is not None:
                stored_tournament.rounds = rounds


class InterclubsJeunesRuleSet(_InterclubsJeunesRuleSet):
    """The divisions the federation runs — Top Jeunes, Nationale 1 and
    Nationale 2: eight boards, the last two playing a second game against
    each other's opponent. Their format and their scoring are those of the
    regulations."""

    STANDARD_BOARD_COUNT = 8
    STANDARD_SECOND_GAME_COUNT = 2
    STANDARD_AGE_LIMITS = (16, 16, 14, 14, 12, 12, 10, 10)

    @property
    @override
    def second_game_count(self) -> int:
        return self.STANDARD_SECOND_GAME_COUNT

    @property
    @override
    def required_pairing_system_id(self) -> str | None:
        """Art. 1.2: "dans chaque groupe, la compétition est organisée selon
        le système toutes rondes"."""
        return 'TEAM_ROUND_ROBIN'

    @override
    def forfeit_win_score(self, board_count: int) -> float | None:
        return 10.0 if board_count == self.STANDARD_BOARD_COUNT else None

    @override
    def forfeit_limit(self, board_count: int) -> int | None:
        return 3 if board_count == self.STANDARD_BOARD_COUNT else None

    @override
    def colour_pattern(self, board_count: int) -> str:
        """Art. 3.2: the first-named team also has white on boards 7 and 8
        for their first game."""
        single = board_count - self.second_game_count
        return _alternating_colours(single) + 'W' * (board_count - single)

    @property
    @override
    def config_fields(self) -> tuple[RuleSetField, ...]:
        return (
            RuleSetField(
                id='division',
                label=_('Division'),
                kind='select',
                default=_DIVISION_NATIONALE_2,
                choices=_division_choices(),
            ),
        )

    @property
    def division(self) -> str:
        return cast(str, self.config_value('division'))

    @property
    @override
    def managed_fields(self) -> set[str]:
        return set(self._shared_values('TEAM_ROUND_ROBIN', None)) | set(
            self._standard_values()
        )

    @override
    def apply_defaults(
        self,
        stored_tournament: StoredTournament,
        pairing_system_id: str | None = None,
    ) -> None:
        self._apply_shared_defaults(stored_tournament, pairing_system_id)
        stored_tournament.cadence = Cadence.STANDARD.value
        stored_tournament.team_player_count = self.STANDARD_BOARD_COUNT
        stored_tournament.color_pattern = self.colour_pattern(self.STANDARD_BOARD_COUNT)
        stored_tournament.match_points = dict(_MATCH_POINTS)
        stored_tournament.primary_score = ScoreType.MATCH_POINTS.value
        stored_tournament.game_points = dict(_GAME_POINTS)

    @override
    def form_defaults(
        self,
        pairing_system_id: str | None = None,
        pairing_variation_id: str | None = None,
    ) -> dict[str, str]:
        return self._standard_values() | self._shared_values(
            pairing_system_id, pairing_variation_id
        )

    @staticmethod
    @override
    def ffe_competition_id() -> int | None:
        return 3

    @property
    @override
    def ffe_division_name(self) -> str | None:
        return {
            _DIVISION_TOP_JEUNES: 'Top Jeunes',
            _DIVISION_NATIONALE_1: 'Nationale I',
            _DIVISION_NATIONALE_2: 'Nationale II',
        }.get(self.division)

    @staticmethod
    @override
    def static_id() -> str:
        return 'ffe-interclubs-jeunes'

    @staticmethod
    @override
    def static_name() -> str:
        return _('FFE youth team championship (Top Jeunes / N1 / N2)')

    @property
    @override
    def description(self) -> str:
        return _(
            'FFE Interclubs Jeunes, national divisions. 8 boards by age '
            'category; boards 7 and 8 play two games, the second against '
            "each other's opponent."
        )


class InterclubsJeunesNationale3RuleSet(_InterclubsJeunesRuleSet):
    """The Nationale 3, which the leagues run under regulations of their
    own: some play a Swiss between dozens of teams, at a faster cadence, or
    agree another number of boards with the federation. The rule set
    starts a tournament with everything the federal regulations say — a
    round robin of four boards, the last one playing its opponent twice
    with the colours of an even board first — and imposes none of it. What
    it keeps to itself is which boards play twice, which the arbiter says,
    a game of those boards being worth half a game of the others."""

    STANDARD_BOARD_COUNT = 4
    STANDARD_SECOND_GAME_COUNT = 1
    STANDARD_AGE_LIMITS = (16, 14, 12, 10)

    @property
    @override
    def config_fields(self) -> tuple[RuleSetField, ...]:
        return (
            RuleSetField(
                id='second_games',
                label=_('Boards playing two games, each for half the points'),
                kind='select',
                default=_SECOND_GAMES_LAST_BOARD,
                choices=_second_games_choices(),
                help_text=_(
                    'A game of these boards scores half the game points set '
                    'below: 1 for a win where the other boards score 2. With '
                    'two such boards, each meets the opponent of the other in '
                    'its second game.'
                ),
                locked_once_paired=True,
            ),
        )

    @override
    def forfeit_win_score(self, board_count: int) -> float | None:
        return 5.0 if self.board_age_limits(board_count) is not None else None

    @override
    def forfeit_limit(self, board_count: int) -> int | None:
        return 1 if self.board_age_limits(board_count) is not None else None

    @property
    @override
    def second_game_count(self) -> int:
        return _SECOND_GAME_COUNTS.get(
            cast(str, self.config_value('second_games')),
            self.STANDARD_SECOND_GAME_COUNT,
        )

    @property
    @override
    def imposes_tie_breaks(self) -> bool:
        return False

    @override
    def rounds_for_pairing(
        self,
        pairing_system_id: str,
        pairing_variation_id: str | None = None,
    ) -> int | None:
        return None

    @override
    def form_prefills(self) -> dict[str, str]:
        """Everything the regulations say of a Nationale 3, the round robin
        first since the other values depend on the pairing system. None of
        it is imposed: the leagues write their own regulations, and pair
        groups too large for a round robin as a Swiss."""
        return (
            {'pairing_system': 'TEAM_ROUND_ROBIN'}
            | self._shared_values(None, None)
            | self._standard_values()
        )

    @staticmethod
    @override
    def static_id() -> str:
        return 'ffe-interclubs-jeunes-n3'

    @staticmethod
    @override
    def static_name() -> str:
        return _('FFE youth team championship (Nationale 3)')

    @property
    @override
    def description(self) -> str:
        return _(
            'FFE Interclubs Jeunes, Nationale 3. By default 4 boards by age '
            'category, board 4 playing its opponent twice; a league may set '
            'another format.'
        )
