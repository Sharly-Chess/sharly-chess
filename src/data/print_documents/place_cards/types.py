from abc import ABC
import random
from datetime import datetime

from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.board import Board
from data.player import Player
from data.print_documents.place_cards.data import (
    PlaceCardPlayer,
    PlaceCardBoard,
    PlaceCardPairing,
)
from data.tournament import Tournament
from utils.entity import IdentifiableEntity
from utils.enum import PlayerRatingType, PlayerGender, PlayerTitle, PlayerCategory


class PlaceCardType(IdentifiableEntity, ABC):
    @staticmethod
    def get_valid_options() -> list[str]:
        """Returns a list of valid options for the place card type."""
        from data.print_documents.options import (
            TournamentPrintOption,
            PlaceCardTemplatePrintOption,
            PlaceCardMirrorPrintOption,
            PlaceCardCropMarksPrintOption,
        )

        return [
            PlaceCardTemplatePrintOption.static_id(),
            TournamentPrintOption.static_id(),
            PlaceCardMirrorPrintOption.static_id(),
            PlaceCardCropMarksPrintOption.static_id(),
        ]

    @staticmethod
    def get_random_player(
        last_name: str,
        color: str = '',
    ) -> PlaceCardPlayer:
        place_card_player: PlaceCardPlayer = PlaceCardPlayer()
        place_card_player.rating = str(random.randint(1400, 3000))
        place_card_player.rating_type = random.choice(
            [
                PlayerRatingType.FIDE,
                PlayerRatingType.NATIONAL,
                PlayerRatingType.ESTIMATED,
            ]
        ).short_name
        place_card_player.last_name = last_name
        place_card_player.first_name = _('First name')
        place_card_player.full_name = Player.player_full_name(
            place_card_player.first_name,
            place_card_player.last_name,
        )
        year: int = datetime.now().year
        place_card_player.year_of_birth = str(random.randint(year - 100, year - 5))
        place_card_player.gender = PlayerGender(
            random.choice(PlayerGender.values())
        ).short_name
        place_card_player.title = PlayerTitle(
            random.choice(PlayerTitle.values())
        ).short_name
        place_card_player.federation = random.choice(
            list(SharlyChessConfig().federations.keys())
        )
        place_card_player.club = _("Player's club")
        place_card_player.category = PlayerCategory(
            random.choice(PlayerCategory.values())
        ).short_name
        place_card_player.color = color
        return place_card_player

    @classmethod
    def players(
        cls,
        tournament: Tournament,
        player_ids: list[int] | None = None,
    ) -> list[PlaceCardPlayer]:
        return []

    @classmethod
    def preview_players(
        cls,
    ) -> list[PlaceCardPlayer]:
        return []

    @classmethod
    def boards(
        cls,
        tournament: Tournament,
        board_numbers: set[int] | None = None,
    ) -> list[PlaceCardBoard]:
        return []

    @classmethod
    def preview_boards(
        cls,
    ) -> list[PlaceCardBoard]:
        return []

    @classmethod
    def pairings(
        cls,
        tournament: Tournament,
        round_: int,
        board_numbers: set[int] | None = None,
    ) -> list[PlaceCardPairing]:
        return []

    @classmethod
    def preview_pairings(
        cls,
    ) -> list[PlaceCardPairing]:
        return []

    @property
    def mirror_rotate(self) -> bool:
        return True


class PlayerCardType(PlaceCardType):
    @staticmethod
    def static_id() -> str:
        return 'player'

    @staticmethod
    def static_name() -> str:
        return _('Player Cards')

    @staticmethod
    def get_valid_options() -> list[str]:
        from data.print_documents.options import PlayersPrintOption

        return PlaceCardType.get_valid_options() + [
            PlayersPrintOption.static_id(),
        ]

    @classmethod
    def players(
        cls,
        tournament: Tournament,
        player_ids: list[int] | None = None,
    ) -> list[PlaceCardPlayer]:
        players: list[Player] = list(tournament.players_by_starting_rank.values())
        if player_ids:
            players = [player for player in players if player.id in player_ids]
        return [PlaceCardPlayer(player) for player in players]

    @classmethod
    def preview_players(
        cls,
    ) -> list[PlaceCardPlayer]:
        return [
            cls.get_random_player(_("PLAYER'S NAME")),
        ]


class BoardCardType(PlaceCardType):
    @staticmethod
    def static_id() -> str:
        return 'board'

    @staticmethod
    def static_name() -> str:
        return _('Board Cards')

    @staticmethod
    def get_valid_options() -> list[str]:
        from data.print_documents.options import (
            PlaceCardBoardNumbersPrintOption,
        )

        return PlaceCardType.get_valid_options() + [
            PlaceCardBoardNumbersPrintOption.static_id(),
        ]

    @classmethod
    def get_random_board(
        cls,
    ) -> PlaceCardBoard:
        return PlaceCardBoard(random.randint(1, 99))

    @classmethod
    def boards(
        cls,
        tournament: Tournament,
        board_numbers: set[int] | None = None,
        preview: bool = False,
    ) -> list[PlaceCardBoard]:
        if preview:
            return [cls.get_random_board()]
        elif board_numbers:
            return [PlaceCardBoard(board_number) for board_number in board_numbers]
        else:
            return [
                PlaceCardBoard(board_number)
                for board_number in sorted(
                    [
                        tournament.first_board_number - 1 + number
                        for number in range(tournament.player_count // 2)
                    ]
                    + [
                        player.fixed
                        for player in tournament.players_by_id.values()
                        if player.fixed
                    ]
                )
            ]

    @classmethod
    def preview_boards(
        cls,
    ) -> list[PlaceCardBoard]:
        return [
            cls.get_random_board(),
        ]


class PairingCardType(PlaceCardType):
    @staticmethod
    def static_id() -> str:
        return 'pairing'

    @staticmethod
    def static_name() -> str:
        return _('Pairing Cards')

    @property
    def mirror_rotate(self) -> bool:
        return False

    @staticmethod
    def get_valid_options() -> list[str]:
        from data.print_documents.options import (
            RoundPrintOption,
            PlaceCardBoardNumbersPrintOption,
        )

        return PlaceCardType.get_valid_options() + [
            RoundPrintOption.static_id(),
            PlaceCardBoardNumbersPrintOption.static_id(),
        ]

    @classmethod
    def get_random_pairing(
        cls,
    ) -> PlaceCardPairing:
        place_card_pairing: PlaceCardPairing = PlaceCardPairing()
        place_card_pairing.number = random.randint(1, 99)
        place_card_pairing.white_player = cls.get_random_player(
            last_name=_('WHITE PLAYER'),
            color=_('W *** WHITE COLOR FOR PLACE CARDS'),
        )
        place_card_pairing.black_player = cls.get_random_player(
            last_name=_('BLACK PLAYER'),
            color=_('B *** BLACK COLOR FOR PLACE CARDS'),
        )
        return place_card_pairing

    @classmethod
    def pairings(
        cls,
        tournament: Tournament,
        round_: int,
        board_numbers: set[int] | None = None,
    ) -> list[PlaceCardPairing]:
        boards: list[Board] = tournament.get_round_boards(round_)
        if board_numbers:
            boards = [board for board in boards if board.number in board_numbers]
        return [PlaceCardPairing(board) for board in boards]

    @classmethod
    def preview_pairings(
        cls,
    ) -> list[PlaceCardPairing]:
        return [
            cls.get_random_pairing(),
        ]
