from abc import ABC, abstractmethod
from collections.abc import Callable
from copy import copy
from datetime import date

from common.exception import ImporterError, OptionError
from common.i18n import _
from data.event import Event
from data.input_output.tournament_importer_options import (
    TournamentImporterOption,
    FileOption,
)
from data.loader import EventLoader
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredTournament,
    StoredPlayer,
    StoredBoard,
)
from utils.date_time import format_date
from utils.enum import Result
from utils.option import OptionHandler


class TournamentImporter(OptionHandler[TournamentImporterOption], ABC):
    def __init__(self, options: list[TournamentImporterOption] | None = None):
        super().__init__(options)
        self.stored_event_modified = False
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

    @property
    def check_in_imported(self) -> bool:
        """Defines if the player's check-in status is imported by the importer."""
        return False

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
    ) -> int:
        """Load a tournament into an event.
        If tournament is provided, update this tournament, otherwise create a new one.
        Returns the ID of the tournament.
        Raises if the tournament already has players."""
        existing_stored_tournament: StoredTournament | None = None
        if tournament:
            existing_stored_tournament = copy(tournament.stored_tournament)
            existing_stored_tournament.stored_tournament_players = []
        stored_tournament, stored_players = self.load_stored_tournament(
            event, existing_stored_tournament
        )
        self.check_players_unicity(stored_players)
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
            if self.stored_event_modified:
                database.update_stored_event(event.stored_event)
        event = EventLoader().load_event(event.uniq_id)
        tournament = event.tournaments_by_id[tournament_id]
        tournament.set_tournament_players_pairing_numbers()
        if not self.check_in_imported:
            with EventDatabase(event.uniq_id, True) as database:
                database.set_players_check_in(
                    [player.id for player in tournament.tournament_players],
                    tournament.default_player_check_in,
                )
        for task in self.post_import_task:
            task(tournament)
        return tournament.id

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
            stored_tournament.id = database.add_stored_tournament(stored_tournament)
        tournament_id = stored_tournament.id
        assert tournament_id is not None
        if stored_tournament.pairing_settings:
            database.set_tournament_pairing_settings(
                tournament_id, stored_tournament.pairing_settings
            )
        database.delete_all_tournament_stored_tie_breaks(tournament_id)
        for index, stored_tie_break in enumerate(stored_tournament.stored_tie_breaks):
            stored_tie_break.tournament_id = tournament_id
            stored_tie_break.index = index
            database.add_stored_tie_break(stored_tie_break)

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
        for stored_tournament_player in stored_tournament.stored_tournament_players:
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
            stored_tournament_player.player_id: {
                stored_pairing.round_: stored_pairing
                for stored_pairing in stored_tournament_player.stored_pairings
            }
            for stored_tournament_player in stored_tournament.stored_tournament_players
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

    @classmethod
    def check_players_unicity(cls, stored_players: list[StoredPlayer]):
        fide_ids: list[int] = []
        name_keys: list[tuple[str, str | None, date]] = []
        for player in stored_players:
            if player.date_of_birth:
                name_key = player.last_name, player.first_name, player.date_of_birth
                if name_key in name_keys:
                    raise ImporterError(
                        _('Player [{player}] is duplicated.').format(
                            player=(
                                f'{player.last_name} {player.first_name} '
                                f'{format_date(player.date_of_birth)}'
                            )
                        )
                    )
                name_keys.append(name_key)
            if fide_id := player.fide_id:
                if fide_id in fide_ids:
                    raise ImporterError(
                        _('Player with FIDE ID [{fide_id}] is duplicated.').format(
                            fide_id=fide_id
                        )
                    )
                fide_ids.append(fide_id)


class FileTournamentImporter(TournamentImporter, ABC):
    @staticmethod
    def available_options() -> list[type[TournamentImporterOption]]:
        return [FileOption]

    @property
    def on_file_selected_post_route_name(self) -> str | None:
        """POST route called when a file is selected."""
        return None

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
