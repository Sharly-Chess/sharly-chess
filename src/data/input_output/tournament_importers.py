from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime

import trf
from trf import Game as TrfGame
from trf import Player as TrfPlayer
from trf import Tournament as TrfTournament
from trf.TrfException import TrfException

from common.exception import ImporterError, OptionError, SharlyChessException
from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.event import Event
from data.input_output.tournament_importer_options import (
    TournamentImporterOption,
    FileOption,
    TournamentRatingOption,
)
from data.input_output.trf_mappers import (
    TrfPlayerGender,
    TrfPlayerTitle,
    TrfColor,
    TrfResult,
)
from data.loader import EventLoader
from data.pairings.variations import StandardSwissVariation
from data.player import PlayerRating
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredTournament,
    StoredPlayer,
    StoredTournamentPlayer,
    StoredBoard,
    StoredPairing,
)
from utils.enum import TournamentRating, Result, BoardColor, PlayerRatingType
from utils.option import OptionHandler


class TournamentImporter(OptionHandler[TournamentImporterOption], ABC):
    def __init__(self, options: list[TournamentImporterOption] | None = None):
        super().__init__(options)
        self.post_import_task: list[Callable[[Tournament], None]] = []
        if self.reorder_boards:
            self.post_import_task.append(self._reorder_tournament_boards)

    @property
    def display_in_menu(self) -> bool:
        """Determines if the import is visible in the import menu."""
        return True

    @property
    @abstractmethod
    def modal_title(self) -> str:
        """The title to display in the import modal."""

    @property
    def doc_url(self) -> str | None:
        """The doc URL of the icon to display on the modal header.
        If None, display no icon."""
        return None

    @property
    def reorder_boards(self) -> bool:
        """Determines if the boards need reordering after they've been loaded."""
        return True

    @staticmethod
    def _reorder_tournament_boards(tournament: Tournament):
        with EventDatabase(tournament.event.uniq_id, True) as database:
            for round_ in range(1, tournament.rounds + 1):
                tournament.set_for_round(round_)
                boards = tournament.get_round_boards(round_)
                for index, board in enumerate(sorted(boards, reverse=True)):
                    board.stored_board.index = index
                    database.update_stored_board(board.stored_board)

    def on_import_finished(self):
        """Function to execute when the import process ends, whether it fails or succeeds."""

    def validate_options(self, event: Event | None = None):
        super().validate_options()

    @abstractmethod
    def load_stored_tournament(
        self,
        event: Event,
        stored_tournament: StoredTournament | None = None,
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        """Load the tournament file into stored objects.
        Use the ids from the source to link data.
        If a StoredTournament object is provided, add the values to this one,
        otherwise creates a new one.
        Should not update the name of the tournament.
        Raise an OptionError for an error displayed on a form element.
        Raise an ImporterError for an error displayed on the head of the form.
        Raise a SharlyChessException for an error to log.
        """

    def load_tournament(
        self,
        event: Event,
        tournament: Tournament | None = None,
    ) -> Tournament:
        """Load a tournament into an event.
        If tournament is provided, update this tournament, otherwise create a new one.
        Raises if the tournament already has players."""
        stored_tournament, stored_players = self.load_stored_tournament(
            event, tournament.stored_tournament if tournament else None
        )
        self.check_pairing_inconsistencies(stored_tournament)
        with EventDatabase(event.uniq_id, True) as database:
            if tournament:
                database.delete_players_in_tournament(tournament.id)
            else:
                stored_tournament.name = event.get_unused_tournament_name(
                    stored_tournament.name
                )
            tournament_id = self._write_stored_tournament(
                stored_tournament, stored_players, database
            )
        event = EventLoader().load_event(event.uniq_id)
        tournament = event.tournaments_by_id[tournament_id]
        tournament.set_players_pairing_numbers()
        for task in self.post_import_task:
            task(tournament)
        return tournament

    @staticmethod
    def _write_stored_tournament(
        stored_tournament: StoredTournament,
        stored_players: list[StoredPlayer],
        database: EventDatabase,
    ) -> int:
        """Writes the content of the stored tournament to the Database.
        Remaps all the ids used. Returns the tournament id."""
        if stored_tournament.id:
            database.update_stored_tournament(stored_tournament)
        else:
            stored_tournament.id = database.add_stored_tournament(stored_tournament).id
        tournament_id = stored_tournament.id
        assert tournament_id is not None
        if stored_tournament.pairing_settings:
            database.set_tournament_pairing_settings(
                tournament_id, stored_tournament.pairing_settings
            )
        database.set_tournament_check_in(tournament_id, stored_tournament.check_in_open)

        # Players
        player_id_by_external_id: dict[int, int] = {}
        for stored_player in stored_players:
            external_id = stored_player.id
            stored_player.id = None
            player_id = database.add_stored_player(stored_player)
            if external_id is not None:
                player_id_by_external_id[external_id] = player_id
            stored_player.id = player_id

        # Boards
        board_id_by_external_id: dict[int, int] = {}
        for stored_boards in stored_tournament.stored_boards_by_round.values():
            for stored_board in stored_boards:
                external_id = stored_board.id
                stored_board.id = None
                stored_board.white_player_id = player_id_by_external_id[
                    stored_board.white_player_id
                ]
                if stored_board.black_player_id is not None:
                    stored_board.black_player_id = player_id_by_external_id[
                        stored_board.black_player_id
                    ]
                board_id = database.add_stored_board(stored_board)
                assert external_id is not None
                board_id_by_external_id[external_id] = board_id
                stored_board.id = board_id

        # Tournament players
        for stored_player in stored_players:
            stored_tournament_player = stored_player.stored_tournament_player
            stored_tournament_player.tournament_id = tournament_id
            stored_tournament_player.player_id = player_id_by_external_id[
                stored_tournament_player.player_id
            ]
            for stored_pairing in stored_tournament_player.stored_pairings:
                stored_pairing.tournament_id = tournament_id
                stored_pairing.player_id = player_id_by_external_id[
                    stored_pairing.player_id
                ]
                if stored_pairing.board_id:
                    stored_pairing.board_id = board_id_by_external_id[
                        stored_pairing.board_id
                    ]
            database.add_stored_tournament_player(stored_tournament_player)
        return tournament_id

    _asymmetric_to_symmetric_results: dict[
        tuple[Result, Result], tuple[Result, Result]
    ] = {
        (Result.LOSS, Result.LOSS): (Result.PENALTY_LL, Result.PENALTY_LL),
        (Result.LOSS, Result.DRAW): (Result.PENALTY_LD, Result.PENALTY_DL),
        (Result.DRAW, Result.LOSS): (Result.PENALTY_DL, Result.PENALTY_LD),
        (Result.UNRATED_LOSS, Result.UNRATED_LOSS): (
            Result.UNRATED_PENALTY_LL,
            Result.UNRATED_PENALTY_LL,
        ),
        (Result.UNRATED_LOSS, Result.UNRATED_DRAW): (
            Result.UNRATED_PENALTY_LD,
            Result.UNRATED_PENALTY_DL,
        ),
        (Result.UNRATED_DRAW, Result.UNRATED_LOSS): (
            Result.UNRATED_PENALTY_DL,
            Result.UNRATED_PENALTY_LD,
        ),
        (Result.FORFEIT_LOSS, Result.FORFEIT_LOSS): (
            Result.DOUBLE_FORFEIT,
            Result.DOUBLE_FORFEIT,
        ),
    }

    @classmethod
    def check_pairing_inconsistencies(cls, stored_tournament: StoredTournament):
        """Check if the pairings of the tournament are coherent.
        If the incoherence can be rectified, it is,
        otherwise raises an ImporterError."""
        pairings_by_round_by_player_id = {
            stored_player.id: {
                stored_pairing.round_: stored_pairing
                for stored_pairing in stored_player.stored_tournament_player.stored_pairings
            }
            for stored_player in stored_tournament.stored_players
        }
        boards_by_id: dict[int, StoredBoard] = {}
        for round_, stored_boards in stored_tournament.stored_boards_by_round.items():
            for stored_board in stored_boards:
                assert stored_board.id is not None
                boards_by_id[stored_board.id] = stored_board

        for player_id, pairings_by_round in pairings_by_round_by_player_id.items():
            for round_, pairing in pairings_by_round.items():
                error_prefix = _('Player [{player_id}] - round {round}: ').format(
                    player_id=player_id, round=round_
                )
                result = Result(pairing.result)
                if pairing.board_id is None:
                    if not result.is_no_board_bye and result != Result.NO_RESULT:
                        raise ImporterError(
                            error_prefix
                            + _(
                                "Result [{result}] can't be used without a board."
                            ).format(result=result.to_trf)
                        )
                    continue

                if result.is_no_board_bye:
                    raise ImporterError(
                        error_prefix
                        + _("Result [{result}] can't be used with a board.").format(
                            result=result.to_trf
                        )
                    )
                if pairing.board_id not in boards_by_id:
                    raise ImporterError(
                        error_prefix
                        + _('Reference to unknown board [{board_id}].').format(
                            board_id=pairing.board_id
                        )
                    )
                board = boards_by_id[pairing.board_id]
                if player_id not in (board.white_player_id, board.black_player_id):
                    raise ImporterError(
                        error_prefix
                        + _('Link to a board not involving the player.').format(
                            board_id=pairing.board_id
                        )
                    )
                other_player_id = (
                    board.white_player_id
                    if player_id == board.black_player_id
                    else board.black_player_id
                )
                if result.is_board_bye:
                    if other_player_id is not None:
                        raise ImporterError(
                            error_prefix
                            + _(
                                "Result [{result}] can't be used with an opponent."
                            ).format(result=result.to_trf)
                        )
                    continue
                if other_player_id is None:
                    raise ImporterError(
                        error_prefix
                        + _(
                            "Result [{result}] can't be used without an opponent."
                        ).format(result=result.to_trf)
                    )
                if other_player_id not in pairings_by_round_by_player_id:
                    raise ImporterError(
                        error_prefix
                        + _('Reference to unknown player [{player_id}].').format(
                            player_id=other_player_id
                        )
                    )
                if round_ not in pairings_by_round_by_player_id[player_id]:
                    raise ImporterError(
                        _('Player [{player_id}] - round {round}: ').format(
                            player_id=other_player_id, round=round_
                        )
                        + _('Pairing not found.')
                    )
                other_pairing = pairings_by_round_by_player_id[other_player_id][round_]
                if other_pairing.board_id != pairing.board_id:
                    raise ImporterError(
                        error_prefix + _("Board is not the same as the opponent's.")
                    )
                other_result = Result(other_pairing.result)
                if other_result == result.opposite_result:
                    continue
                if (result, other_result) not in cls._asymmetric_to_symmetric_results:
                    raise ImporterError(
                        error_prefix
                        + _(
                            'Result [{result}] is incompatible with the '
                            "opponent's result [{opponent_result}]."
                        ).format(
                            result=result.to_trf,
                            opponent_result=other_result.to_trf,
                        )
                    )
                result, other_result = cls._asymmetric_to_symmetric_results[
                    (result, other_result)
                ]
                pairing.result = result.value
                other_pairing.result = other_result.value


class FileTournamentImporter(TournamentImporter, ABC):
    @staticmethod
    def available_options() -> list[type[TournamentImporterOption]]:
        return [FileOption]

    @property
    @abstractmethod
    def accepted_file_suffixes(self) -> list[str]:
        """List of suffixes accepted by the file input."""

    def validate_options(self, event: Event | None = None):
        super().validate_options()
        file_option = self._get_option(FileOption)
        suffix = file_option.value.suffix
        if suffix not in self.accepted_file_suffixes:
            raise OptionError(
                _('File has invalid suffix [{suffix}] (expected: {expected}).').format(
                    suffix=suffix,
                    expected=', '.join(self.accepted_file_suffixes),
                ),
                file_option,
            )

    def on_import_finished(self):
        file_path = self._get_option(FileOption).value
        if file_path:
            try:
                file_path.unlink(missing_ok=True)
            except OSError:
                pass


class TrfTournamentImporter(FileTournamentImporter):
    @staticmethod
    def static_id() -> str:
        return 'TRF'

    @staticmethod
    def static_name() -> str:
        return _('TRF file')

    @staticmethod
    def available_options() -> list[type[TournamentImporterOption]]:
        return [
            FileOption,
            TournamentRatingOption,
        ]

    @property
    def modal_title(self) -> str:
        return _('Import TRF file')

    @property
    def accepted_file_suffixes(self) -> list[str]:
        return ['.trf', '.trfx']

    def load_stored_tournament(
        self, event: Event, stored_tournament: StoredTournament | None = None
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        (file_path, tournament_rating) = self.get_option_values()
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                trf_tournament = trf.load(file)
        except TrfException as exception:
            raise SharlyChessException(str(exception))
        stored_tournament = self._read_trf_tournament(trf_tournament, stored_tournament)
        stored_tournament.rating = tournament_rating
        next_board_id = 1
        board_id_by_player_id_by_round: dict[int, dict[int, int]] = defaultdict(dict)
        stored_boards_by_round: dict[int, list[StoredBoard]] = defaultdict(list)
        stored_players: list[StoredPlayer] = []
        for trf_player in trf_tournament.players:
            player_id = trf_player.startrank
            try:
                self._validate_trf_player(trf_player)
            except ImporterError as exception:
                raise ImporterError(
                    _('Player [{player_id}]: {error}').format(
                        player_id=player_id,
                        error=exception,
                    )
                )
            stored_player = self._read_trf_player(
                trf_player, TournamentRating(tournament_rating)
            )
            stored_tournament_player = StoredTournamentPlayer(
                player_id=player_id,
                pairing_number=trf_player.startrank,
            )
            for trf_game in trf_player.games:
                if trf_game.round > stored_tournament.rounds:
                    stored_tournament.rounds = trf_game.round
                round_nb = trf_game.round
                try:
                    self._validate_trf_game(trf_game)
                except ImporterError as exception:
                    raise ImporterError(
                        _('Player [{player_id}] - round {round}: ').format(
                            player_id=player_id,
                            round=round_nb,
                        )
                        + str(exception)
                    )
                stored_pairing, stored_board = self._read_trf_game(trf_game, player_id)
                if stored_board:
                    if player_id in board_id_by_player_id_by_round[round_nb]:
                        board_id = board_id_by_player_id_by_round[round_nb][player_id]
                    else:
                        board_id = next_board_id
                        next_board_id += 1
                        stored_board.id = board_id
                        stored_boards_by_round[round_nb].append(stored_board)
                        if trf_game.startrank:
                            board_id_by_player_id_by_round[round_nb][
                                trf_game.startrank
                            ] = board_id
                    stored_pairing.board_id = board_id
                stored_tournament_player.stored_pairings.append(stored_pairing)
            stored_player.stored_tournament_player = stored_tournament_player
            stored_players.append(stored_player)
        stored_tournament.stored_boards_by_round = stored_boards_by_round
        if stored_boards_by_round:
            stored_tournament.rounds = max(tuple(stored_boards_by_round))
        return stored_tournament, stored_players

    @staticmethod
    def _validate_trf_player(trf_player: TrfPlayer):
        try:
            TrfPlayerGender.get_core_object(trf_player.sex)
        except KeyError:
            raise ImporterError(
                _('Unknown gender [{gender}].').format(gender=trf_player.sex)
            )
        try:
            TrfPlayerTitle.get_core_object(trf_player.title)
        except KeyError:
            raise ImporterError(
                _('Unknown title [{title}].').format(title=trf_player.title)
            )
        if (
            trf_player.fed
            and trf_player.fed.upper() not in SharlyChessConfig.federations
        ):
            raise ImporterError(
                _('Unknown federation [{federation}].').format(
                    federation=trf_player.fed.upper()
                )
            )
        if trf_player.birthdate:
            try:
                datetime.strptime(trf_player.birthdate, '%Y/%m/%d')
            except ValueError:
                raise ImporterError(
                    _('Invalid date format [{date}] (expected: {format})').format(
                        date=trf_player.birthdate, format='YYYY/MM/DD'
                    )
                )

    @staticmethod
    def _validate_trf_game(trf_game: TrfGame):
        try:
            color = TrfColor.get_core_object(trf_game.color)
        except KeyError:
            raise ImporterError(
                _('Unknown color [{color}].').format(color=trf_game.color)
            )
        try:
            result = TrfResult.get_core_object(
                trf_game.result, has_opponent=bool(trf_game.startrank)
            )
        except KeyError:
            raise ImporterError(
                _('Unknown result [{result}].').format(result=trf_game.result)
            )

        if trf_game.startrank and result.is_bye:
            raise ImporterError(
                _("Result [{result}] can't be used with an opponent.").format(
                    result=trf_game.result
                )
            )
        if not trf_game.startrank and not (result.is_bye or result == Result.NO_RESULT):
            raise ImporterError(
                _("Result [{result}] can't be used without an opponent.").format(
                    result=trf_game.result
                )
            )
        if trf_game.startrank and not color:
            raise ImporterError(
                _("Color [{color}] can't be used with an opponent.").format(
                    color=trf_game.color
                )
            )
        if not trf_game.startrank and color:
            raise ImporterError(
                _("Color [{color}] can't be used without an opponent.").format(
                    color=trf_game.color
                )
            )

    @staticmethod
    def _read_trf_tournament(
        trf_tournament: TrfTournament,
        stored_tournament: StoredTournament | None = None,
    ) -> StoredTournament:
        if not stored_tournament:
            stored_tournament = StoredTournament(id=None, name=trf_tournament.name)
        stored_tournament.pairing = StandardSwissVariation.static_id()
        stored_tournament.location = trf_tournament.city
        return stored_tournament

    @staticmethod
    def _read_trf_player(
        trf_player: TrfPlayer, tournament_rating: TournamentRating
    ) -> StoredPlayer:
        ratings = {
            tr.value: PlayerRating(0, PlayerRatingType.ESTIMATED).stored_value
            for tr in TournamentRating
        }
        if trf_player.rating:
            ratings[tournament_rating.value] = PlayerRating(
                trf_player.rating, PlayerRatingType.FIDE
            ).stored_value
        return StoredPlayer(
            id=trf_player.startrank,
            last_name=trf_player.name.split(',')[0].strip().upper(),
            ratings=ratings,
            first_name=(
                trf_player.name.split(',')[1].strip()
                if ',' in trf_player.name
                else None
            ),
            gender=TrfPlayerGender.get_core_object(trf_player.sex).value,
            title=TrfPlayerTitle.get_core_object(trf_player.title).value,
            fide_id=trf_player.id,
            date_of_birth=(
                datetime.strptime(trf_player.birthdate, '%Y/%m/%d').date()
                if trf_player.birthdate
                else None
            ),
            federation=trf_player.fed.upper() or 'FID',
        )

    @staticmethod
    def _read_trf_game(
        trf_game: TrfGame, player_id: int
    ) -> tuple[StoredPairing, StoredBoard | None]:
        stored_board: StoredBoard | None = None
        result = TrfResult.get_core_object(
            trf_game.result, has_opponent=bool(trf_game.startrank)
        )
        color = TrfColor.get_core_object(trf_game.color)
        stored_pairing = StoredPairing(
            tournament_id=0,
            player_id=player_id,
            round_=trf_game.round,
            result=result.value,
            board_id=None,
        )
        if trf_game.startrank:
            stored_board = StoredBoard(
                id=None,
                white_player_id=(
                    player_id if color == BoardColor.WHITE else trf_game.startrank
                ),
                black_player_id=(
                    trf_game.startrank if color == BoardColor.WHITE else player_id
                ),
                index=0,
            )
        elif result.is_board_bye:
            stored_board = StoredBoard(
                id=None,
                white_player_id=player_id,
                black_player_id=None,
                index=0,
            )
        return stored_pairing, stored_board
