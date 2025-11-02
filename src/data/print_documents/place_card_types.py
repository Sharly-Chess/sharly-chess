from abc import ABC
from typing import TYPE_CHECKING, Any

from common import BASE_DIR
from common.i18n import _
from data.board import Board
from data.print_documents.place_card_entities import PlaceCardBoard, PlaceCardPlayer
from database.sqlite.event.event_store import StoredBoard
from utils.entity import IdentifiableEntity
from utils.file import image_file_inline_url

if TYPE_CHECKING:
    from data.print_documents.documents import (
        PlaceCardPrintDocument,
    )


class PlaceCardType(IdentifiableEntity, ABC):
    @staticmethod
    def get_valid_options() -> list[str]:
        """Returns a list of valid options for the place card type."""
        from data.print_documents.options import (
            TournamentPrintOption,
            PlaceCardTemplatePrintOption,
        )

        return [
            PlaceCardTemplatePrintOption.static_id(),
            TournamentPrintOption.static_id(),
        ]

    @classmethod
    def flag_inline_urls_by_federation(
        cls,
        federation_names: set[str],
    ) -> dict[str, str]:
        """Returns a dict with the inline URLs of the federations passed."""
        return {
            federation_name: image_file_inline_url(
                BASE_DIR / f'src/web/static/images/federations/{federation_name}.svg'
            )
            for federation_name in federation_names
        }

    def template_context(
        self,
        doc: 'PlaceCardPrintDocument',
    ) -> dict[str, Any]:
        return {}


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

    def template_context(
        self,
        doc: 'PlaceCardPrintDocument',
    ) -> dict[str, Any]:
        players = doc.tournament.players_by_starting_rank.values()
        federation_names = set(player.federation.name for player in players)
        return {
            'players': (PlaceCardPlayer(player) for player in players),
            'flag_inline_urls_by_federation': self.flag_inline_urls_by_federation(
                federation_names
            ),
        }


class BoardCardType(PlaceCardType):
    @staticmethod
    def static_id() -> str:
        return 'board'

    @staticmethod
    def static_name() -> str:
        return _('Board Cards')

    def template_context(
        self,
        doc: 'PlaceCardPrintDocument',
    ) -> dict[str, Any]:
        players = doc.tournament.players_by_id.values()
        board_numbers = [
            doc.tournament.first_board_number - 1 + number
            for number in range(doc.tournament.player_count // 2)
        ] + [player.fixed for player in players if player.fixed]
        first_player_id: int = list(doc.tournament.players_by_id.keys())[0]
        boards = [
            Board(
                doc.tournament,
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
        federation_names = set(player.federation.name for player in players)
        return {
            'boards': (PlaceCardBoard(board) for board in boards),
            'flag_inline_urls_by_federation': self.flag_inline_urls_by_federation(
                federation_names
            ),
        }


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
