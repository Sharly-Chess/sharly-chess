"""Pairing and unpairing, board by board.

A round's boards are what the engine, the importer or the arbiter make
of them: a pairing seats two players at a table, an unpairing frees
it, and a table number is found for whoever is left waiting. Every
change is written to the event database and mirrored in the loaded
tournament.
"""

from typing import TYPE_CHECKING

from common.exception import SharlyChessException
from data.board import Board
from data.pairings.engines import TeamPairingEngine
from data.pairings.fixed_table import FixedTablePairingEngine
from data.teams.team_board import TeamBoard
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredBoard,
    StoredTeamBoard,
    set_stored_fields,
)
from utils.enum import Result, TeamByeType

if TYPE_CHECKING:
    from data.tournament import Tournament


class BoardOperations:
    """The pairings and unpairings of one tournament's boards."""

    def __init__(self, tournament: 'Tournament') -> None:
        self.tournament = tournament

    def pab_board(self, round_: int) -> Board | None:
        """The round's pairing-allocated-bye board — a player seated alone,
        *waiting* for an opponent. A flat-system forfeit hole is also
        black-less but is a settled result (``FORFEIT_WIN``), not an empty
        bye, so it's excluded: manual pairing must not attach a new player
        to a legitimate forfeit board."""
        return next(
            (
                board
                for board in self.tournament.boards_by_id.values()
                if board.round == round_
                and not board.black_tournament_player
                and board.result == Result.PAIRING_ALLOCATED_BYE
            ),
            None,
        )

    def unboarded_holes(self, round_: int) -> list[tuple[int, str]]:
        """Flat fixed-table (Molter): empty table cells with no board this
        round — absent seats, e.g. freed by unpairing and awaiting a forfeit
        pairing. Each is ``(board_index, label)`` like ``(5, 'B3')``. Empty
        for other systems. A present-but-unpaired player's seat isn't a hole
        (it's filled in the lineup); only ``None`` slots count."""
        tournament = self.tournament
        engine = tournament.pairing_variation.engine
        if not isinstance(engine, FixedTablePairingEngine):
            return []
        refs = engine.board_references(tournament, round_)
        team_by_letter = engine.team_by_letter(tournament)
        boarded = {board.index for board in tournament.get_round_boards(round_)}
        holes: list[tuple[int, str]] = []
        for index, (white_ref, black_ref) in enumerate(refs):
            if index in boarded:
                continue
            for ref in (white_ref, black_ref):
                team = team_by_letter.get(ref[0])
                if team is None:
                    continue
                slot = int(ref[1:]) - 1
                slots = team.effective_round_slots(round_)
                if 0 <= slot < len(slots) and slots[slot] is None:
                    holes.append((index, ref))
        return holes

    def create_flat_manual(
        self,
        round_: int,
        white_id: int | None,
        black_id: int | None,
        index: int,
    ) -> None:
        """Create one flat (Molter) board from a manual selection. Either side
        may be ``None`` (a hole) — but not both. Two players ⇒ a game; one
        player + a hole ⇒ a forfeit win for the present player (handled by
        :meth:`create`, which scores a one-sided flat board as a
        forfeit). No lineup is touched."""
        if white_id is None and black_id is None:
            raise SharlyChessException('A board needs at least one player.')
        for player_id in (white_id, black_id):
            if player_id is None:
                continue
            pairing = self.tournament.tournament_players_by_id[player_id].pairings[
                round_
            ]
            if pairing.exists and pairing.stored_pairing.board_id is not None:
                raise SharlyChessException(
                    f'Player {player_id} is already paired in round {round_}.'
                )
        self.create(
            [
                StoredBoard(
                    id=None,
                    white_player_id=white_id,
                    black_player_id=black_id,
                    index=index,
                )
            ],
            round_,
            Result.FORFEIT_WIN,
        )

    def available_indexes(self, round_: int) -> list[int]:
        tournament = self.tournament
        board_indexes = [
            board.index
            for board in tournament.get_round_boards(round_)
            if not board.exempt
        ]
        max_board_count = (
            len(tournament.tournament_players) // 2
            + len(tournament.tournament_players) % 2
        )
        return [index for index in range(max_board_count) if index not in board_indexes]

    def first_unused_index(self, round_: int) -> int:
        """Smallest table index occupied by NO board this round — counting
        one-sided forfeit (exempt) boards, which still own a real table.
        Unlike :meth:`available_indexes` (which frees an exempt
        bye's index for reuse), this never reuses a hole's index, so a manual
        flat pairing can't be placed on top of an existing forfeit table."""
        used = {board.index for board in self.tournament.get_round_boards(round_)}
        index = 0
        while index in used:
            index += 1
        return index

    def pab_index(
        self,
        round_: int,
        new_indexes: list[int] | None = None,
    ) -> int:
        board_indexes = [
            board.index
            for board in self.tournament.get_round_boards(round_)
            if not board.exempt
        ] + (new_indexes or [])
        if not board_indexes:
            return 0
        return max(board_indexes) + 1

    def _delete_board(self, board: Board, database: EventDatabase) -> None:
        """Take the board out of the round: its players lose their pairing
        for it, its row goes, and so does its entry in the loaded boards."""
        for player in (
            board.optional_white_tournament_player,
            board.black_tournament_player,
        ):
            if player is not None:
                player.delete_pairing(board.round, database)
                player.reset_board()
        database.delete_stored_board(board.identifier)
        self.tournament.boards_by_id.pop(board.identifier, None)

    def pair(
        self, round_nb: int, white_player_id: int, black_player_id: int | None
    ) -> Board:
        """Creates a pairing for a round."""
        tournament = self.tournament
        white_tournament_player = tournament.tournament_players_by_id[white_player_id]
        black_tournament_player = (
            tournament.tournament_players_by_id[black_player_id]
            if black_player_id
            else None
        )
        white_pairing = white_tournament_player.pairings[round_nb]
        black_pairing = (
            black_tournament_player.pairings[round_nb]
            if black_tournament_player
            else None
        )

        if white_pairing.opponent_id:
            raise ValueError(
                f'White player {white_tournament_player.full_name} already has an '
                f'opponent (id: {white_pairing.opponent_id}) for round {round_nb}.'
            )
        if black_tournament_player and black_pairing and black_pairing.opponent_id:
            raise ValueError(
                f'Black player {black_tournament_player.full_name} already has an '
                f'opponent (id: {black_pairing.opponent_id}) for round {round_nb}.'
            )
        with EventDatabase(tournament.event.uniq_id, True) as database:
            if black_tournament_player and black_pairing:
                result = Result.NO_RESULT
                board = self.pab_board(round_nb)
                assert board is not None
                board_id = board.identifier
                board.index = self.available_indexes(round_nb)[0]
                board.replace_player(black_tournament_player, 'black')
                # Re-freeze the fixed number now the second seat is filled.
                set_stored_fields(
                    board.stored_board, fixed_number=board.live_fixed_number or 0
                )
                black_pairing.stored_pairing.result = result.value
                black_pairing.stored_pairing.board_id = board_id
                black_pairing.update(database)
                database.update_stored_board(board.stored_board)
            else:
                result = Result.PAIRING_ALLOCATED_BYE
                # Fill the first free table index (a hole left by an unpaired
                # board), not the end — so a manually paired player lands on
                # the lowest vacant table rather than after the last one.
                available_indexes = self.available_indexes(round_nb)
                stored_board = StoredBoard(
                    id=None,
                    white_player_id=white_tournament_player.id,
                    black_player_id=None,
                    index=available_indexes[0] if available_indexes else 0,
                )
                board = Board(tournament, round_nb, stored_board)
                set_stored_fields(
                    stored_board, fixed_number=board.live_fixed_number or 0
                )
                board_id = database.add_stored_board(stored_board)
                set_stored_fields(stored_board, id=board_id)
                tournament.boards_by_id[board_id] = board
            white_pairing.stored_pairing.result = result.value
            white_pairing.stored_pairing.board_id = board_id
            white_pairing.update(database)
        return board

    def pair_teams(self, round_: int, team_id: int) -> TeamBoard:
        """Manual team pairing — mirrors :meth:`pair`.

        If a PAB envelope (team_b is None, not a manual bye) already
        exists for the round, completes the pair: the existing team
        becomes ``team_a``, *team_id* becomes ``team_b``, individual
        boards are regenerated with both lineups and their results
        flipped from PAB to NO_RESULT. Otherwise creates a fresh PAB
        envelope for *team_id* (with its lineup populated against an
        empty opposing side, just like an engine-assigned bye)."""
        tournament = self.tournament
        engine = tournament.pairing_variation.engine
        assert isinstance(engine, TeamPairingEngine)
        round_list = (
            tournament.stored_tournament.stored_team_boards_by_round.setdefault(
                round_, []
            )
        )
        manual_bye_types = TeamByeType.manual_bye_types()
        pab_stb = next(
            (
                stb
                for stb in round_list
                if stb.team_b_id is None and stb.bye_type not in manual_bye_types
            ),
            None,
        )
        on_board_team_ids: set[int] = set()
        for stb in round_list:
            if stb.team_b_id is None and stb.bye_type in manual_bye_types:
                continue
            on_board_team_ids.add(stb.team_a_id)
            if stb.team_b_id is not None:
                on_board_team_ids.add(stb.team_b_id)
        if team_id in on_board_team_ids and (
            pab_stb is None or pab_stb.team_a_id != team_id
        ):
            raise ValueError(
                f'Team {team_id} already has a team-board for round {round_}.'
            )
        completing_pair = pab_stb is not None and pab_stb.team_a_id != team_id
        stored_boards: list[StoredBoard] = []
        new_stb: StoredTeamBoard | None = None
        boards_to_delete: list[int] = []
        with EventDatabase(tournament.event.uniq_id, write=True) as database:
            # Clear any existing manual bye envelope (HPB/FPB/ZPB) for
            # this team — pairing supersedes it.
            existing_byes = [
                stb
                for stb in round_list
                if stb.team_a_id == team_id
                and stb.team_b_id is None
                and stb.bye_type in manual_bye_types
            ]
            for bye_stb in existing_byes:
                if bye_stb.id is not None:
                    database.delete_stored_team_board(bye_stb.id)
                round_list.remove(bye_stb)
            if completing_pair:
                assert pab_stb is not None
                # Drop the PAB-side individual boards; new ones with
                # both lineups will be built below.
                boards_to_delete.extend(
                    board.identifier
                    for board in list(tournament.boards_by_id.values())
                    if board.stored_board.team_board_id == pab_stb.id
                )
                for board_id in boards_to_delete:
                    deleted_board = tournament.boards_by_id.get(board_id)
                    if deleted_board is not None:
                        self._delete_board(deleted_board, database)
                pab_stb.team_b_id = team_id
                pab_stb.bye_type = None
                database.update_stored_team_board(pab_stb)
                stored_boards = engine._team_match_stored_boards(tournament, pab_stb)
            else:
                # Reuse the first free table number — like individual manual
                # pairing, a hole left by an unpaired match is filled rather
                # than always appending at the end (hidden byes hold NULL).
                used_indexes = {
                    stb.index for stb in round_list if stb.index is not None
                }
                next_index = 0
                while next_index in used_indexes:
                    next_index += 1
                new_stb = StoredTeamBoard(
                    id=None,
                    tournament_id=tournament.id,
                    round_=round_,
                    team_a_id=team_id,
                    team_b_id=None,
                    index=next_index,
                    bye_type=None,
                )
                new_stb.id = database.add_stored_team_board(new_stb)
                round_list.append(new_stb)
                stored_boards = engine._team_match_stored_boards(tournament, new_stb)
        tournament.clear_team_cache()
        self.create(stored_boards, round_, Result.PAIRING_ALLOCATED_BYE)
        # Whichever of the two branches above ran assigned the one read here.
        target_stb = pab_stb if completing_pair else new_stb
        assert target_stb is not None
        assert target_stb.id is not None
        return tournament.team_boards_by_id[target_stb.id]

    def unpair_team(self, team_board: TeamBoard) -> None:
        """Unpair a single team match. Deletes the team_board envelope
        and every individual board under it, but leaves the rest of
        the round (other team_boards, manual byes) intact."""
        tournament = self.tournament
        round_ = team_board.round
        stb_id = team_board.stored_team_board.id
        assert stb_id is not None
        boards_to_delete = [
            board
            for board in tournament.boards_by_id.values()
            if board.stored_board.team_board_id == stb_id
        ]
        with EventDatabase(tournament.event.uniq_id, write=True) as database:
            for board in boards_to_delete:
                self._delete_board(board, database)
            database.delete_stored_team_board(stb_id)
            for team_id in (
                team_board.stored_team_board.team_a_id,
                team_board.stored_team_board.team_b_id,
            ):
                if team_id is not None:
                    tournament.point_adjustments.set_manual(
                        team_id, round_, 0.0, 0.0, None, database
                    )
            round_list = tournament.stored_tournament.stored_team_boards_by_round.get(
                round_, []
            )
            tournament.stored_tournament.stored_team_boards_by_round[round_] = [
                stb for stb in round_list if stb.id != stb_id
            ]
        tournament.clear_team_cache()

    def unpair(self, boards: list[Board]) -> None:
        tournament = self.tournament
        rounds: set[int] = set()
        with EventDatabase(tournament.event.uniq_id, True) as database:
            for board in boards:
                rounds.add(board.round)
                # The game is gone, so its manual bonus / penalty goes
                # with it.
                for player in (
                    board.optional_white_tournament_player,
                    board.black_tournament_player,
                ):
                    if player is not None:
                        tournament.point_adjustments.set_manual_for_player(
                            player.id, board.round, 0.0, None, database
                        )
                self._delete_board(board, database)
            for round_ in rounds:
                if pab_board := self.pab_board(round_):
                    pab_board.index = self.pab_index(round_)
                    database.update_stored_board(pab_board.stored_board)
            if tournament.event.is_team_event:
                manual_bye_types = TeamByeType.manual_bye_types()
                for round_ in rounds:
                    round_list = (
                        tournament.stored_tournament.stored_team_boards_by_round.get(
                            round_, []
                        )
                    )
                    kept: list[StoredTeamBoard] = []
                    for stb in round_list:
                        is_manual_bye = (
                            stb.team_b_id is None and stb.bye_type in manual_bye_types
                        )
                        if is_manual_bye:
                            kept.append(stb)
                        elif stb.id is not None:
                            database.delete_stored_team_board(stb.id)
                            # The match is gone, so its manual bonus /
                            # penalty goes with it.
                            for team_id in (stb.team_a_id, stb.team_b_id):
                                if team_id is not None:
                                    tournament.point_adjustments.set_manual(
                                        team_id, round_, 0.0, 0.0, None, database
                                    )
                    if kept:
                        tournament.stored_tournament.stored_team_boards_by_round[
                            round_
                        ] = kept
                    else:
                        tournament.stored_tournament.stored_team_boards_by_round.pop(
                            round_, None
                        )
        if tournament.event.is_team_event:
            tournament.clear_team_cache()

    def create(
        self, stored_boards: list[StoredBoard], round_: int, pab_result: Result
    ) -> None:
        tournament = self.tournament
        with EventDatabase(tournament.event.uniq_id, True) as database:
            if pab_board := self.pab_board(round_):
                pab_board.index = self.pab_index(
                    round_, [board.index for board in stored_boards]
                )
                database.update_stored_board(pab_board.stored_board)
            for stored_board in stored_boards:
                board = Board(tournament, round_, stored_board)
                if stored_board.fixed_number is None:
                    # Freeze the fixed table number now so a later edit to a
                    # player's fixed table can't renumber this round.
                    set_stored_fields(
                        stored_board, fixed_number=board.live_fixed_number or 0
                    )
                id_ = database.add_stored_board(stored_board)
                set_stored_fields(stored_board, id=id_)
                tournament.boards_by_id[id_] = board
                white_pairing = board.optional_white_pairing
                black_pairing = board.optional_black_pairing
                # Reset every pairing this loop touches so any stale
                # result from a prior round-pairing (e.g. ZPB on a
                # player who was absent before being paired in) doesn't
                # leak through. The hole / PAB branches below override
                # this explicitly.
                for p in (white_pairing, black_pairing):
                    if p is None:
                        continue
                    p.stored_pairing.board_id = id_
                    p.stored_pairing.result = Result.NO_RESULT.value
                    p.stored_pairing.effective_points = None
                    p.stored_pairing.illegal_moves = 0
                present_pairing = white_pairing or black_pairing
                if present_pairing is not None and not (
                    white_pairing is not None and black_pairing is not None
                ):
                    parent_team_board_id = stored_board.team_board_id
                    parent_team_board = (
                        tournament.team_boards_by_id.get(parent_team_board_id)
                        if parent_team_board_id is not None
                        else None
                    )
                    if (
                        parent_team_board is not None
                        and parent_team_board.stored_team_board.team_b_id is not None
                    ):
                        # Real team match, hole on the opposing side ⇒
                        # forfeit win for the present player.
                        present_pairing.stored_pairing.result = Result.FORFEIT_WIN.value
                    else:
                        # PAB envelope (or individual-mode bye) ⇒ PAB.
                        present_pairing.stored_pairing.result = pab_result.value
                if white_pairing is not None:
                    white_pairing.update(database)
                if black_pairing is not None:
                    black_pairing.update(database)
