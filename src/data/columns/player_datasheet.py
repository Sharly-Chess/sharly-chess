from abc import abstractmethod, ABC
from typing import Any

from data.player import Player
from utils.enum import TournamentRating, PlayerRatingType
from web.utils import PlayerColumn


class DatasheetColumn(PlayerColumn, ABC):
    @property
    @abstractmethod
    def header_content(self) -> str:
        pass

    @abstractmethod
    def get_cell_content(self, player: Player) -> Any:
        pass


class LastNameColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'last_name'

    def get_cell_content(self, player: Player) -> Any:
        return player.last_name


class FirstNameColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'first_name'

    def get_cell_content(self, player: Player) -> Any:
        return player.first_name


class YearOfBirthColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'yob'

    def get_cell_content(self, player: Player) -> Any:
        return player.year_of_birth or ''


class MailColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'mail'

    def get_cell_content(self, player: Player) -> Any:
        return player.mail or ''


class PhoneColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'phone'

    def get_cell_content(self, player: Player) -> Any:
        return player.phone or ''


class GenderColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'gender'

    def get_cell_content(self, player: Player) -> Any:
        return player.gender.short_name


class FideIDColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'fide_id'

    def get_cell_content(self, player: Player) -> Any:
        return player.fide_id or ''


class TournamentColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'tournament'

    def get_cell_content(self, player: Player) -> Any:
        return player.tournament.name


class FederationColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'federation'

    def get_cell_content(self, player: Player) -> Any:
        return player.federation.name


class ClubColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'club'

    def get_cell_content(self, player: Player) -> Any:
        return player.club.name


class OwedColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'owed'

    def get_cell_content(self, player: Player) -> Any:
        return player.owed


class PaidColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'paid'

    def get_cell_content(self, player: Player) -> Any:
        return player.paid


class CommentColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'comment'

    def get_cell_content(self, player: Player) -> Any:
        return player.comment or ''


class RatingColumn(DatasheetColumn):
    def __init__(
        self, tournament_type: TournamentRating, rating_type: PlayerRatingType
    ):
        self.tournament_type = tournament_type
        self.rating_type = rating_type

    @property
    def header_content(self) -> str:
        tournament = self.tournament_type.short_name
        rating = self.rating_type.short_name
        return f'{tournament}_{rating}'.lower()

    def get_cell_content(self, player: Player) -> Any:
        return (
            player.ratings[self.tournament_type].get_type_value(self.rating_type) or ''
        )
