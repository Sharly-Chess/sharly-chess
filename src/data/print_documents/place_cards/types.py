from abc import ABC

from common.i18n import _
from data.board import Board
from data.player import Player
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredBoard
from utils.entity import IdentifiableEntity


class PlaceCardType(IdentifiableEntity, ABC):
    @staticmethod
    def get_valid_options() -> list[str]:
        """Returns a list of valid options for the place card type."""
        from data.print_documents.options import (
            TournamentPrintOption,
            PlaceCardTemplatePrintOption,
            PlaceCardMirrorPrintOption,
            PlaceCardCuttingPrintOption,
        )

        return [
            PlaceCardTemplatePrintOption.static_id(),
            TournamentPrintOption.static_id(),
            PlaceCardMirrorPrintOption.static_id(),
            PlaceCardCuttingPrintOption.static_id(),
        ]

    @staticmethod
    def boards(
        tournament: Tournament,
        round_: int,
    ) -> list[Board]:
        return []

    @staticmethod
    def players(
        tournament: Tournament,
    ) -> list[Player]:
        return []


class PlayerCardType(PlaceCardType):
    @staticmethod
    def static_id() -> str:
        return 'player'

    @staticmethod
    def static_name() -> str:
        return _('Player Cards')

    @staticmethod
    def get_valid_options() -> list[str]:
        return (
            PlaceCardType.get_valid_options()
            + [
                # TODO add a player multi-select
            ]
        )

    @staticmethod
    def players(
        tournament: Tournament,
    ) -> list[Player]:
        return list(tournament.players_by_starting_rank.values())


class BoardCardType(PlaceCardType):
    @staticmethod
    def static_id() -> str:
        return 'board'

    @staticmethod
    def static_name() -> str:
        return _('Board Cards')

    @staticmethod
    def boards(
        tournament: Tournament,
        round_: int,
    ) -> list[Board]:
        players = tournament.players_by_id.values()
        board_numbers = [
            tournament.first_board_number - 1 + number
            for number in range(tournament.player_count // 2)
        ] + [player.fixed for player in players if player.fixed]
        first_player_id: int = list(tournament.players_by_id.keys())[0]
        return [
            Board(
                tournament,
                1,
                StoredBoard(
                    board_number,
                    first_player_id,
                    None,
                    board_number,
                ),
            )
            for board_number in board_numbers
        ]


class PairingCardType(PlaceCardType):
    @staticmethod
    def static_id() -> str:
        return 'pairing'

    @staticmethod
    def static_name() -> str:
        return _('Pairing Cards')

    @staticmethod
    def get_valid_options() -> list[str]:
        from data.print_documents.options import RoundPrintOption

        return PlaceCardType.get_valid_options() + [
            RoundPrintOption.static_id(),
        ]

    @staticmethod
    def boards(
        tournament: Tournament,
        round_: int,
    ) -> list[Board]:
        return tournament.get_round_boards(round_)
