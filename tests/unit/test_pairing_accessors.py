from data.pairing import Pairing
from database.sqlite.event.event_store import StoredBoard, StoredPairing
from utils.enum import BoardColor, Result


class TournamentStub:
    def __init__(self):
        self.boards_by_id = {}


class TournamentPlayerStub:
    def __init__(self, id_: int, tournament: TournamentStub):
        self.id = id_
        self.tournament = tournament


class BoardStub:
    def __init__(
        self,
        white: TournamentPlayerStub,
        black: TournamentPlayerStub | None,
    ):
        self.stored_board = StoredBoard(
            id=10,
            white_player_id=white.id,
            black_player_id=black.id if black else None,
            index=1,
        )
        self.optional_white_tournament_player = white
        self.black_tournament_player = black


def make_pairing(player: TournamentPlayerStub, result: Result = Result.NO_RESULT):
    return Pairing(
        player,  # type: ignore[arg-type]
        StoredPairing(
            tournament_id=1,
            player_id=player.id,
            round_=1,
            result=result.value,
            board_id=10,
        ),
    )


def test_result_tracks_stored_value_changes():
    player = TournamentPlayerStub(1, TournamentStub())
    pairing = make_pairing(player, Result.WIN)

    assert pairing.result == Result.WIN
    pairing.stored_pairing.result = Result.LOSS.value
    assert pairing.result == Result.LOSS


def test_board_side_and_opponent_accessors():
    tournament = TournamentStub()
    white = TournamentPlayerStub(1, tournament)
    black = TournamentPlayerStub(2, tournament)
    tournament.boards_by_id[10] = BoardStub(white, black)

    white_pairing = make_pairing(white)
    black_pairing = make_pairing(black)

    assert white_pairing.color == BoardColor.WHITE
    assert white_pairing.opponent is black
    assert white_pairing.opponent_id == black.id
    assert black_pairing.color == BoardColor.BLACK
    assert black_pairing.opponent is white
    assert black_pairing.opponent_id == white.id


def test_hole_has_no_opponent():
    tournament = TournamentStub()
    white = TournamentPlayerStub(1, tournament)
    tournament.boards_by_id[10] = BoardStub(white, None)

    pairing = make_pairing(white)

    assert pairing.color == BoardColor.WHITE
    assert pairing.opponent is None
    assert pairing.opponent_id is None
