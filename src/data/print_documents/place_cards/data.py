import logging
from datetime import date

from common.i18n import _
from common.logger import get_logger

from plugins.manager import plugin_manager

from data.board import Board
from data.event import Event
from data.player import Player
from data.tournament import Tournament

logger: logging.Logger = get_logger()


class PlaceCardPlayer:
    """A utility class to pass unmodifiable players' data to print documents."""

    def __init__(
        self,
        player: Player | None = None,
        color: str = '',
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
        self.club: str = ''
        self.category: str = ''
        self.color: str = ''
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
            self.club = player.club.name
            self.category = player.category.short_name
            self.color = color
            plugin_manager.hook_for_event(player.event, 'augment_place_card_player')(
                player=player, place_card_player=self
            )

    @property
    def federation_flag(self) -> str:
        return (
            f'<img class="federation-flag {self.federation}" />'
            if self.federation
            else ''
        )


class PlaceCardBoard:
    """A utility class to pass unmodifiable boards' data to print documents."""

    def __init__(
        self,
        number: int,
    ):
        self.number: int = number


class PlaceCardPairing:
    """A utility class to pass unmodifiable pairings' data to print documents."""

    def __init__(
        self,
        board: Board | None = None,
    ):
        self.number: int
        self.white_player: PlaceCardPlayer
        self.black_player: PlaceCardPlayer
        if board:
            self.number = board.number
            self.white_player = PlaceCardPlayer(
                board.white_player, color=_('W *** WHITE COLOR FOR PLACE CARDS')
            )
            self.black_player = PlaceCardPlayer(
                board.black_player, color=_('B *** BLACK COLOR FOR PLACE CARDS')
            )
        else:
            self.number = 0
            self.white_player = PlaceCardPlayer()
            self.black_player = PlaceCardPlayer()


class PlaceCardDate:
    """A utility class to pass unmodifiable dates to print documents."""

    def __init__(self, date_: date):
        self.year: int = date_.year
        self.month: int = date_.month
        self.day: int = date_.day


class PlaceCardTournament:
    """A utility class to pass unmodifiable tournaments' data to print documents."""

    def __init__(
        self,
        tournament: Tournament | None = None,
    ):
        self.name: str
        self.start: PlaceCardDate
        self.stop: PlaceCardDate
        if tournament:
            self.name = tournament.name
            self.start = PlaceCardDate(tournament.stop_date)
            self.stop = PlaceCardDate(tournament.stop_date)
        else:
            self.name = _('Tournament name')
            today = date.today()
            self.start = PlaceCardDate(today)
            self.stop = PlaceCardDate(today)


class PlaceCardEvent:
    """A utility class to pass unmodifiable tournaments' data to print documents."""

    def __init__(
        self,
        event: Event | None = None,
    ):
        self.name: str
        self.start: PlaceCardDate
        self.stop: PlaceCardDate
        if event:
            self.name = event.name
            self.start = PlaceCardDate(event.start_date)
            self.stop = PlaceCardDate(event.stop_date)
        else:
            self.name = _('Event name')
            today = date.today()
            self.start = PlaceCardDate(today)
            self.stop = PlaceCardDate(today)
