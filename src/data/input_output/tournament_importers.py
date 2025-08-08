from abc import ABC, abstractmethod
from pathlib import Path

from common.exception import SharlyChessException
from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTournament, StoredPlayer
from utils.entity import IdentifiableEntity


class TournamentImporter(IdentifiableEntity, ABC):
    @property
    @abstractmethod
    def reorder_boards(self) -> bool:
        """Determines if the boards need reordering after they've been loaded."""

    @abstractmethod
    def load_stored_tournament(
        self,
        source_file: Path,
        stored_tournament: StoredTournament | None = None,
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        """Load the tournament file into stored objects.
        Use the ids from the source to link data.
        If a StoredTournament object is provided, add the values to this one,
        otherwise creates a new one.
        """

    def load_tournament(
        self,
        source_file: Path,
        event: Event,
        tournament: Tournament | None = None,
    ) -> Tournament:
        """Load a tournament into an event.
        If tournament is provided, update this tournament, otherwise create a new one.
        Raises if the already has players."""
        if tournament and tournament.players:
            raise SharlyChessException(
                'Impossible to import into a tournament already having players.'
            )
        stored_tournament, stored_players = self.load_stored_tournament(
            source_file, tournament.stored_tournament if tournament else None
        )
        if not tournament:
            stored_tournament.uniq_id = event.get_unused_tournament_uniq_id(
                stored_tournament.uniq_id
            )
        with EventDatabase(event.uniq_id, True) as database:
            tournament_id = self._write_stored_tournament(
                stored_tournament, stored_players, database
            )
            database.commit()
            event = EventLoader().reload_event(event.uniq_id)
            tournament = event.tournaments_by_id[tournament_id]
            if self.reorder_boards:
                for round_ in range(1, tournament.rounds + 1):
                    tournament.set_for_round(round_)
                    boards = tournament.get_round_boards(round_)
                    for index, board in enumerate(sorted(boards, reverse=True)):
                        board.stored_board.index = index
                        database.update_stored_board(board.stored_board)
                database.commit()
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
            stored_tournament = database.add_stored_tournament(stored_tournament)
        tournament_id = stored_tournament.id
        assert tournament_id is not None
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
        for _, stored_boards in stored_tournament.stored_boards_by_round.items():
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
