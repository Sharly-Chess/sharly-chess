import base64
from abc import ABC
from pathlib import Path
from typing import TYPE_CHECKING, Any

from common import BASE_DIR
from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.board import Board
from database.sqlite.event.event_store import StoredBoard
from utils.entity import IdentifiableEntity

if TYPE_CHECKING:
    from data.print_documents.documents import (
        PlaceCardPrintDocument,
        PrintCardPlayer,
        PrintCardTournament,
        PrintCardEvent,
        PrintCardBoard,
    )


class PlaceCardType(IdentifiableEntity, ABC):
    @staticmethod
    def get_valid_options() -> list[str]:
        """Returns a list of valid options for the place card type."""
        from data.print_documents.options import TournamentPrintOption

        return [
            TournamentPrintOption.static_id(),
        ]

    @staticmethod
    def base654_encode_file(
        file: Path,
    ) -> str:
        with open(file, 'rb') as f:
            data: bytes = f.read()
        return base64.b64encode(data).decode('utf-8')

    @classmethod
    def ttf_inline_url(
        cls,
    ) -> str:
        """Returns the inline URL for a TTF file (this method is used to build self-contained files)."""
        font_file: Path = (
            BASE_DIR / 'src/web/static/fonts/AtkinsonHyperlegibleNextVF-Variable.ttf'
        )
        encoded_data = cls.base654_encode_file(font_file)
        return f'data:font/truetype;charset=utf-8;base64,{encoded_data}'

    @classmethod
    def svg_file_inline_url(
        cls,
        file: Path,
    ) -> str:
        """Returns the inline URL for a SVG file (this method is used to build self-contained files)."""
        encoded_data = cls.base654_encode_file(file)
        image_type = file.suffix.lower().replace('.', '').replace('\\n', '')
        return f'data:image/{image_type}+xml;base64,{encoded_data}'

    @classmethod
    def flag_inline_urls_by_federation(
        cls,
        federation_names: set[str],
    ) -> dict[str, str]:
        """Returns a dict with the inline URLs of the federations passed."""
        return {
            federation_name: cls.svg_file_inline_url(
                BASE_DIR / f'src/web/static/images/federations/{federation_name}.svg'
            )
            for federation_name in federation_names
        }

    @classmethod
    def template_context(
        cls,
        doc: 'PlaceCardPrintDocument',
    ) -> dict[str, Any]:
        assert doc.event is not None
        return {
            'sharly_chess_config': SharlyChessConfig(),
            'sharly_chess_font_inline_url': cls.ttf_inline_url(),
            'sharly_chess_logo_inline_url': cls.svg_file_inline_url(
                BASE_DIR / 'src/web/static/images/sharly-chess-logo.svg'
            ),
            'event': PrintCardEvent(doc.event),
            'tournament': PrintCardTournament(doc.tournament),
        }

    @classmethod
    def template_name(cls) -> str:
        return f'/admin/print/place_cards/simple_{cls.static_id()}.html'


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

    @classmethod
    def template_context(
        cls,
        doc: 'PlaceCardPrintDocument',
    ) -> dict[str, Any]:
        players = doc.tournament.players_by_starting_rank.values()
        federation_names = set(player.federation.name for player in players)
        return PlaceCardType.template_context(doc) | {
            'players': (PrintCardPlayer(player) for player in players),
            'flag_inline_urls_by_federation': cls.flag_inline_urls_by_federation(
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

    @classmethod
    def template_context(
        cls,
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
        return PlaceCardType.template_context(doc) | {
            'boards': (PrintCardBoard(board) for board in boards),
            'flag_inline_urls_by_federation': cls.flag_inline_urls_by_federation(
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
