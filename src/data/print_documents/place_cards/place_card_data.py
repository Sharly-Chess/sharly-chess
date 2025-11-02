import logging
from datetime import datetime

from common.logger import get_logger
from data.board import Board
from data.event import Event
from data.player import Player
from data.tournament import Tournament

logger: logging.Logger = get_logger()


class PlaceCardPlayer:
    """A utility class to pass unmodifiable players' data to print documents."""

    def __init__(
        self,
        player: Player | None,
    ):
        self.rating: str = ''
        self.rating_type: str = ''
        self.full_name: str = ''
        self.first_name: str = ''
        self.last_name: str = ''
        self.year_of_birth: str = ''
        self.gender: str = ''
        self.title: str = ''
        self.federation: str = ''
        self.federation_flag: str = ''
        self.club: str = ''
        self.category: str = ''
        if player:
            if player.rating:
                self.rating = str(player.rating)
            self.rating_type = player.rating_type.short_name
            self.full_name = player.full_name
            self.first_name = player.first_name
            self.last_name = player.last_name
            if player.year_of_birth:
                self.year_of_birth = str(player.year_of_birth)
            self.gender = player.gender.short_name
            self.title = player.title.short_name
            self.federation = player.federation.name
            self.federation_flag = f'<img class="federation-flag {self.federation}" />'
            self.club = player.club.name
            self.category = player.category.short_name


class PlaceCardBoard:
    """A utility class to pass unmodifiable boards' data to print documents."""

    def __init__(
        self,
        board: Board,
    ):
        self.id: int = board.id
        self.number: int = board.number
        self.white_player: PlaceCardPlayer = PlaceCardPlayer(board.white_player)
        self.black_player: PlaceCardPlayer = PlaceCardPlayer(board.black_player)


class PlaceCardDate:
    """A utility class to pass unmodifiable dates to print documents."""

    def __init__(
        self,
        timestamp: float,
    ):
        dt: datetime = datetime.fromtimestamp(timestamp)
        self.year: int = dt.year
        self.month: int = dt.month
        self.day: int = dt.day


class PlaceCardTournament:
    """A utility class to pass unmodifiable tournaments' data to print documents."""

    def __init__(
        self,
        tournament: Tournament,
    ):
        self.name: str = tournament.name
        self.start: PlaceCardDate = PlaceCardDate(tournament.start_timestamp)
        self.stop: PlaceCardDate = PlaceCardDate(tournament.stop_timestamp)


class PlaceCardEvent:
    """A utility class to pass unmodifiable tournaments' data to print documents."""

    def __init__(
        self,
        event: Event,
    ):
        self.name: str = event.name
        self.start: PlaceCardDate = PlaceCardDate(event.start)
        self.stop: PlaceCardDate = PlaceCardDate(event.stop)
