import re
from datetime import datetime
from abc import abstractmethod, ABC
from typing import Any

from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.event import Event
from data.player import Player
from database.sqlite.event.event_store import StoredPlayer
from utils import Utils
from utils.date_time import format_date
from utils.enum import TournamentRating, PlayerRatingType, PlayerGender, PlayerTitle
from utils.types import PlayerRating


class DatasheetColumn(ABC):
    """Column of the datasheet, both used for player export and import."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Identifier of the column."""

    @abstractmethod
    def get_cell_content(self, player: Player) -> Any:
        """Get the content of a cell of the datasheet from a player."""

    @property
    def is_required(self) -> bool:
        """Defines if the column is required."""
        return False

    @property
    def is_unique(self) -> bool:
        """Defines if the values in the column should be unique.
        Null values are ignored."""
        return False

    def augment_stored_player_with_event(
        self, event: Event, stored_player: StoredPlayer, value: str
    ):
        """Save the data of the cell value."""
        if self.is_required and not value:
            raise ValueError(_('This field is required.'))
        self._augment_stored_player(stored_player, value)

    @property
    def save_stored_event(self) -> bool:
        """Defines if the stored event should be saved after the import."""
        return False

    @property
    def export_only(self) -> bool:
        """Defines if the column is only exported but not imported."""
        return False

    @abstractmethod
    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        """Augment the stored player object from a cell value.
        Raise a ValueError if the value is not valid."""


class TitleColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'title'

    def get_cell_content(self, player: Player) -> Any:
        return player.title.value

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        try:
            PlayerTitle(value)
            stored_player.title = value
        except ValueError:
            raise ValueError(
                _('Unknown value (expected: {expected}).').format(
                    expected='|'.join(PlayerTitle)
                )
            )


class LastNameColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'last_name'

    def get_cell_content(self, player: Player) -> Any:
        return player.last_name

    @property
    def is_required(self) -> bool:
        return True

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        stored_player.last_name = value.upper()


class FirstNameColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'first_name'

    def get_cell_content(self, player: Player) -> Any:
        return player.first_name

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        stored_player.first_name = value.title() or None


class DateOfBirthColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'dob'

    def get_cell_content(self, player: Player) -> Any:
        if not player.date_of_birth:
            return ''
        return format_date(player.date_of_birth)

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        if not value:
            return
        formatter = SharlyChessConfig().date_formatter
        try:
            stored_player.date_of_birth = datetime.strptime(
                value, formatter.python_format
            ).date()
        except ValueError:
            raise ValueError(
                _('Invalid format (expected: {format}).').format(
                    format=formatter.humanized_format
                )
            )


class YearOfBirthColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'yob'

    def get_cell_content(self, player: Player) -> Any:
        return player.stored_player.year_of_birth

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        if not value:
            return
        if not value.isdigit() or int(value) == 0:
            raise ValueError(_('A positive integer is expected.'))
        if stored_player.date_of_birth:
            raise ValueError(_('This field is only valid without date of birth.'))
        stored_player.year_of_birth = int(value)


class MailColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'mail'

    def get_cell_content(self, player: Player) -> Any:
        return player.mail

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        if value and not re.match(Utils.EMAIL_REGEX, value):
            raise ValueError(_('Invalid email format.'))
        stored_player.mail = value or None


class PhoneColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'phone'

    def get_cell_content(self, player: Player) -> Any:
        return player.phone

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        stored_player.phone = value or None


class GenderColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'gender'

    def get_cell_content(self, player: Player) -> Any:
        return player.gender.value

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        try:
            PlayerGender(value)
            stored_player.gender = value
        except ValueError:
            raise ValueError(
                _('Unknown value (expected: {expected}).').format(
                    expected='|'.join(PlayerGender)
                )
            )


class TournamentColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'tournament'

    def get_cell_content(self, player: Player) -> Any:
        return player.single_tournament.name

    @property
    def export_only(self) -> bool:
        return True

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        pass


class FederationColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'federation'

    def get_cell_content(self, player: Player) -> Any:
        return player.federation.name

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        if value not in SharlyChessConfig().federations:
            raise ValueError(_('Unknown federation.'))
        stored_player.federation = value


class ClubColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'club'

    def get_cell_content(self, player: Player) -> Any:
        return player.club.name

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        stored_player.club = value or None


class FideIDColumn(DatasheetColumn):
    def __init__(self, is_required: bool = False):
        self._is_required = is_required

    @property
    def id(self) -> str:
        return 'fide_id'

    @property
    def is_required(self) -> bool:
        return self._is_required

    def get_cell_content(self, player: Player) -> Any:
        return player.fide_id

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        if not value:
            return
        if not value.isdigit() or int(value) == 0:
            raise ValueError(_('A positive integer is expected.'))
        stored_player.fide_id = int(value)

    @property
    def is_unique(self) -> bool:
        return True


class FixedColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'fixed'

    def get_cell_content(self, player: Player) -> Any:
        return player.fide_id

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        if not value:
            return
        if not value.isdigit() or int(value) == 0:
            raise ValueError(_('A positive integer is expected.'))
        stored_player.fixed = int(value)


class OwedColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'owed'

    def get_cell_content(self, player: Player) -> Any:
        return player.owed

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        if not value:
            return
        try:
            float_value = float(value)
            if float_value < 0:
                raise ValueError
            stored_player.owed = float_value
        except ValueError:
            raise ValueError(_('A positive float is expected.'))


class PaidColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'paid'

    def get_cell_content(self, player: Player) -> Any:
        return player.paid

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        if not value:
            return
        try:
            float_value = float(value)
            if float_value < 0:
                raise ValueError
            stored_player.paid = float_value
        except ValueError:
            raise ValueError(_('A positive float is expected.'))


class CommentColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'comment'

    def get_cell_content(self, player: Player) -> Any:
        return player.comment

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        stored_player.comment = value or None


class RatingColumn(DatasheetColumn):
    def __init__(
        self, tournament_type: TournamentRating, rating_type: PlayerRatingType
    ):
        self.tournament_type = tournament_type
        self.rating_type = rating_type

    @property
    def id(self) -> str:
        return f'{self.tournament_type.form_key}_{self.rating_type.key}'

    def get_cell_content(self, player: Player) -> Any:
        rating = player.ratings[self.tournament_type]
        return rating.get_type_value(self.rating_type)

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        if not value:
            return
        if not value.isdigit() or int(value) == 0:
            raise ValueError(_('A positive integer is expected.'))
        rating = PlayerRating.from_stored_value(
            stored_player.ratings.get(self.tournament_type.value, {})
        )
        rating.set_value_from_type(int(value), self.rating_type)
        stored_player.ratings[self.tournament_type.value] = rating.stored_value
