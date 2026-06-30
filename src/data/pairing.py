import weakref
from typing import TYPE_CHECKING, Optional
from collections import namedtuple


from logging import Logger
from common.i18n import _
from common.logger import get_logger
from data.board import Board
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPairing
from utils import Utils
from utils.enum import Result, BoardColor, PlayerRatingType

if TYPE_CHECKING:
    from _weakref import ReferenceType
    from data.input_output.trf.trf_data import TrfGame
    from data.player import TournamentPlayer

logger: Logger = get_logger()


RatingChange = namedtuple('RatingChange', ['delta', 'new_rating', 'comment'])


class Pairing:
    """A pairing (from the point of view of the `TournamentPlayer` class)"""

    def __init__(
        self,
        tournament_player: 'TournamentPlayer',
        stored_pairing: StoredPairing,
        exists: bool = True,
    ):
        self._tournament_player_ref: 'ReferenceType[TournamentPlayer]' = weakref.ref(
            tournament_player
        )
        self.stored_pairing = stored_pairing

        # NOTE (Molrn) Flag indicating if the stored object exists in the database or not.
        # Pre-big move, the unpaired rounds had their own *Pairing* objects in the DB
        # This maintains the legacy usages of the *Pairing* class
        # TODO Remove all *Pairing* legacy usages (and this flag)
        self.exists = exists

    @property
    def tournament_player(self) -> 'TournamentPlayer':
        if (tournament_player := self._tournament_player_ref()) is None:
            raise RuntimeError('Reference has been garbage collected')
        return tournament_player

    @property
    def board(self) -> Board | None:
        if not (board_id := self.stored_pairing.board_id):
            return None
        return self.tournament_player.tournament.boards_by_id[board_id]

    @property
    def round(self) -> int:
        return self.stored_pairing.round_

    @property
    def result(self) -> Result:
        return Result(self.stored_pairing.result)

    @property
    def points(self) -> float:
        return self.result.points(self.tournament_player.point_values)

    @property
    def points_str(self) -> str:
        return Utils.points_str(self.points)

    @property
    def illegal_moves(self) -> int:
        return self.stored_pairing.illegal_moves

    def update_result(self, event_database: EventDatabase, result: Result):
        self.stored_pairing.result = result.value
        self.update(event_database)

    def update(self, event_database: EventDatabase):
        if self.exists:
            event_database.update_stored_pairing(self.stored_pairing)
        else:
            event_database.add_stored_pairing(self.stored_pairing)
            self.exists = True

    def add_illegal_move(self, event_database: EventDatabase):
        if self.illegal_moves < self.tournament_player.tournament.record_illegal_moves:
            self.stored_pairing.illegal_moves += 1
            self.update(event_database)
            logger.info(
                'An illegal move has been recorded for player [%s].',
                self.tournament_player.id,
            )
            return True
        return False

    def delete_illegal_move(self, event_database: EventDatabase):
        if self.illegal_moves > 0:
            self.stored_pairing.illegal_moves -= 1
            self.update(event_database)
            logger.info(
                'An illegal move has been deleted for player [%s].',
                self.tournament_player.id,
            )
            return True
        else:
            logger.info(
                'No illegal move found for player [%s].',
                self.tournament_player.id,
            )
            return False

    @property
    def zero_point_bye(self) -> bool:
        return self.result == Result.ZERO_POINT_BYE

    @property
    def needs_pairing(self) -> bool:
        return (self.result == Result.NO_RESULT) and (self.opponent_id is None)

    @property
    def paired(self) -> bool:
        return self.board is not None

    @property
    def unpaired(self) -> bool:
        return not self.paired

    @property
    def paired_no_result(self) -> bool:
        return (self.result == Result.NO_RESULT) and (self.opponent_id is not None)

    @property
    def exempt(self) -> bool:
        return self.result.is_board_bye

    @property
    def opponent_was_hole(self) -> bool:
        """True iff this pairing is on a board inside a real team
        match (its ``team_board`` has ``team_b_id`` set) but the
        opposing side of the board is a lineup hole — the player
        has no opponent because the other team didn't have a player
        for this slot. Distinct from a Pairing-Allocated Bye, which
        is a tournament-level bye, not a per-board missing-opponent."""
        board = self.board
        if board is None:
            return False
        if board.stored_board.team_board_id is None:
            return False
        tournament = self.tournament_player.tournament
        team_board = tournament.team_boards_by_id.get(board.stored_board.team_board_id)
        if team_board is None:
            return False
        if team_board.stored_team_board.team_b_id is None:
            return False
        return (
            board.stored_board.white_player_id is None
            or board.stored_board.black_player_id is None
        )

    @property
    def loss(self) -> bool:
        return self.result.is_loss

    @property
    def unrated_loss(self) -> bool:
        return self.result.is_unrated_loss

    @property
    def draw(self) -> bool:
        return self.result.is_draw

    @property
    def unrated_draw(self) -> bool:
        return self.result.is_unrated_draw

    @property
    def win(self) -> bool:
        return self.result.is_win

    @property
    def unrated_gain(self) -> bool:
        return self.result == Result.UNRATED_WIN

    @property
    def half_point_bye(self) -> bool:
        return self.result == Result.HALF_POINT_BYE

    @property
    def full_point_bye(self) -> bool:
        return self.result == Result.FULL_POINT_BYE

    @property
    def forfeit_loss(self) -> bool:
        return self.result == Result.FORFEIT_LOSS

    @property
    def double_forfeit(self) -> bool:
        return self.result == Result.DOUBLE_FORFEIT

    @property
    def forfeit_gain(self) -> bool:
        return self.result == Result.FORFEIT_WIN

    @property
    def unplayed(self) -> bool:
        return self.result.is_unplayed

    @property
    def played(self) -> bool:
        return not self.unplayed

    @property
    def voluntary_unplayed(self) -> bool:
        return self.result.is_voluntary_unplayed

    @property
    def requested_bye(self) -> bool:
        return self.result.is_requested_bye

    @property
    def next_round_bye(self) -> bool:
        return self.result.is_next_round_bye

    def to_trf(self, round_number: int) -> 'TrfGame':
        from data.input_output.trf.trf_data import TrfGame
        from data.input_output.trf.trf_mappers import TrfColor

        opponent_pn = getattr(self.opponent, 'pairing_number', None)
        if self.result.is_bye:
            opponent_id: int | None = 0
        elif opponent_pn is None and self.board is not None:
            # Hole-opponent (team mode): player has a board but no
            # opposing player. TRF requires the opponent field to be
            # present — emit 0000.
            opponent_id = 0
        else:
            opponent_id = opponent_pn
        return TrfGame(
            opponent_id=opponent_id,
            # TRF forbids a colour without an opponent, so drop it for
            # byes *and* hole-opponent boards (team mode), both of which
            # carry opponent ``0000``.
            color=TrfColor.get_outer_value(
                self.color, self.result.is_bye or opponent_id == 0
            ),
            result=self.result.to_trf,
            round=round_number,
        )

    @property
    def color(self) -> BoardColor | None:
        if not (board := self.board):
            return None
        white_tp = board.optional_white_tournament_player
        if white_tp is not None and white_tp.id == self.tournament_player.id:
            return BoardColor.WHITE
        return BoardColor.BLACK

    @property
    def opponent(self) -> Optional['TournamentPlayer']:
        board = self.board
        if not board:
            return None
        if self.color == BoardColor.WHITE:
            return board.black_tournament_player
        return board.optional_white_tournament_player

    def fide_rating_change(self, k_factor: int):
        tournament_player = self.tournament_player
        opponent = self.opponent
        if self.unplayed:
            return RatingChange(None, tournament_player.rating_used_by_fide.value, '')

        assert opponent is not None
        if tournament_player.rating_used_by_fide.type != PlayerRatingType.FIDE:
            return RatingChange(
                None,
                tournament_player.rating_used_by_fide.value,
                _('Player is not yet rated.'),
            )

        if opponent.rating_used_by_fide.type != PlayerRatingType.FIDE:
            return RatingChange(
                None,
                tournament_player.rating_used_by_fide.value,
                _('Unrated opponent.'),
            )

        diff = (
            opponent.rating_used_by_fide.value
            - tournament_player.rating_used_by_fide.value
        )

        # - For players rated below 2650, clamp |diff| to 400.
        # - For players rated 2650 and above, use full difference.
        if tournament_player.rating_used_by_fide.value < 2650:
            if diff > 400:
                diff = 400
            elif diff < -400:
                diff = -400

        # Find matching probability (fallback to last)
        expected = Utils.win_probability(diff)
        delta = round(k_factor * (self.result.point_value - expected), 2)
        new_rating = Utils.round_ranking(
            tournament_player.rating_used_by_fide.value + delta
        )

        comment = ''
        opponent_rating_overridden = not opponent.rating_is_overridden(
            tournament_player.tournament.rating,
            tournament_player.tournament.player_rating_type,
        ) and opponent.will_fide_override_with_standard_rating(
            tournament_player.tournament.rating,
            tournament_player.tournament.player_rating_type,
        )
        player_rating_overridden = not tournament_player.rating_is_overridden(
            tournament_player.tournament.rating,
            tournament_player.tournament.player_rating_type,
        ) and tournament_player.will_fide_override_with_standard_rating(
            tournament_player.tournament.rating,
            tournament_player.tournament.player_rating_type,
        )

        if opponent_rating_overridden and player_rating_overridden:
            comment = _(
                'The FIDE will use the standard ratings of both players for this game ({rating_opponent} and {rating_player}).'
            ).format(
                rating_opponent=opponent.rating_used_by_fide,
                rating_player=tournament_player.rating_used_by_fide,
            )
        elif opponent_rating_overridden:
            comment = _(
                "The FIDE will use the opponent's standard rating for this game ({rating})."
            ).format(rating=opponent.rating_used_by_fide)
        elif player_rating_overridden:
            comment = _(
                "The FIDE will use the player's standard rating for this game ({rating})."
            ).format(rating=tournament_player.rating_used_by_fide)

        return RatingChange(delta, new_rating, comment)

    @property
    def opponent_id(self) -> int | None:
        opponent = self.opponent
        return opponent.id if opponent else None

    def __str__(self):
        return f'{self.__class__.__name__}({self.color} {self.opponent_id} {self.result.to_trf})'

    def __repr__(self):
        return f'{self.__class__.__name__}(player={self.tournament_player!r}, stored_pairing={self.stored_pairing!r}, exists={self.exists!r})'
