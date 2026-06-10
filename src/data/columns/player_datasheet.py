import re
from datetime import datetime
from abc import abstractmethod, ABC
from typing import Any

from text_unidecode import unidecode

from common import SharlyChessException
from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.player import Player, MIN_YOB, MAX_YOB
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredPlayer
from utils import Utils
from utils.date_time import format_date
from utils.enum import TournamentRating, PlayerRatingType, PlayerGender, PlayerTitle
from utils.types import PlayerRating


class DatasheetColumn(ABC):
    """Column of the datasheet, both used for player export and import."""

    def __init__(self):
        self.is_informative = self.export_only
        self.is_required = self.is_default_required

    @property
    @abstractmethod
    def id(self) -> str:
        """Identifier of the column."""

    def update_from_used_columns(self, used_columns: list['DatasheetColumn']):
        """Update the column from the other used columns."""

    @abstractmethod
    def get_cell_content(self, player: Player) -> Any:
        """Get the content of a cell of the datasheet from a player."""

    @property
    def is_default_required(self) -> bool:
        """Defines if the column is required."""
        return False

    @property
    def is_unique(self) -> bool:
        """Defines if the values in the column should be unique.
        Null values are ignored."""
        return False

    def augment_stored_player_with_tournament(
        self, tournament: Tournament | None, stored_player: StoredPlayer, value: str
    ):
        """Save the data of the cell value."""
        if self.is_required and not value:
            raise SharlyChessException(_('This field is required.'))
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
        Raise a SharlyChessException if the value is not valid."""

    def check_data_source_value_match(self, value: str, player: Player) -> bool:
        """Check if an informative cell value matches the
        stored player found in the data source.
        If so, a warning is displayed on the cell."""
        if not self.is_informative or self.export_only:
            return True
        return str(self.get_cell_content(player) or '') == value


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
            raise SharlyChessException(
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
    def is_default_required(self) -> bool:
        return True

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        stored_player.last_name = value.upper()

    def check_data_source_value_match(self, value: str, player: Player) -> bool:
        return unidecode(player.last_name) == unidecode(value.upper())


class FirstNameColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'first_name'

    def get_cell_content(self, player: Player) -> Any:
        return player.first_name

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        stored_player.first_name = value.title() or None

    def check_data_source_value_match(self, value: str, player: Player) -> bool:
        return unidecode(player.first_name) == unidecode(value.title())


class DateOfBirthColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'date_of_birth'

    def get_cell_content(self, player: Player) -> Any:
        if not player.date_of_birth:
            return ''
        return format_date(player.date_of_birth)

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        if not value:
            return
        formatter = SharlyChessConfig().date_formatter
        try:
            dob = datetime.strptime(value, formatter.python_format).date()
            if not (MIN_YOB <= dob.year <= MAX_YOB):
                raise SharlyChessException(
                    _('Invalid year of birth (expected: {min} - {max}).').format(
                        min=MIN_YOB, max=MAX_YOB
                    )
                )
            stored_player.date_of_birth = dob
        except ValueError:
            raise SharlyChessException(
                _('Invalid format (expected: {format}).').format(
                    format=formatter.humanized_format
                )
            )


class YearOfBirthColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'year_of_birth'

    def get_cell_content(self, player: Player) -> Any:
        return player.year_of_birth or None

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        if not value or stored_player.date_of_birth:
            return
        if not value.isdigit() or not (MIN_YOB <= int(value) <= MAX_YOB):
            raise SharlyChessException(
                _('Invalid year of birth (expected: {min} - {max}).').format(
                    min=MIN_YOB, max=MAX_YOB
                )
            )
        stored_player.year_of_birth = int(value)

    def check_data_source_value_match(self, value: str, player: Player) -> bool:
        if player.date_of_birth and not value:
            return True
        return value == str(player.year_of_birth or '')


class MailColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'mail'

    def get_cell_content(self, player: Player) -> Any:
        return player.mail

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        if value and not re.match(Utils.EMAIL_REGEX, value):
            raise SharlyChessException(_('Invalid email format.'))
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
        return player.gender.key

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        try:
            gender = PlayerGender.from_key(value)
            stored_player.gender = gender.value
        except ValueError:
            raise SharlyChessException(
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


class TeamColumn(DatasheetColumn):
    """Team-mode counterpart to :class:`TournamentColumn`. Exports the
    player's team name; on import the value is stashed on the stored
    player and resolved to a team membership after persistence (matched
    by name, created if absent). Optional — a player with no team is
    still imported, they simply aren't assigned to one."""

    @property
    def id(self) -> str:
        return 'team'

    def get_cell_content(self, player: Player) -> Any:
        team = player.team
        return team.name if team is not None else ''

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        stored_player.transient_team_name = value.strip() or None


class FederationColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'federation'

    def get_cell_content(self, player: Player) -> Any:
        return player.federation.name

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        if value not in SharlyChessConfig().federations:
            raise SharlyChessException(_('Unknown federation.'))
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
    @property
    def id(self) -> str:
        return 'fide_id'

    def get_cell_content(self, player: Player) -> Any:
        return player.fide_id

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        if not value:
            return
        if not value.isdigit() or int(value) == 0:
            raise SharlyChessException(_('A positive integer is expected.'))
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
            raise SharlyChessException(_('A positive integer is expected.'))
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
            raise SharlyChessException(_('A positive float is expected.'))


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
            raise SharlyChessException(_('A positive float is expected.'))


class CheckInColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'check_in'

    def get_cell_content(self, player: Player) -> Any:
        return int(player.check_in)

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        stored_player.check_in = value == '1'


class CommentColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'comment'

    def get_cell_content(self, player: Player) -> Any:
        return player.comment

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        stored_player.comment = value or None


class RatingColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'rating'

    def get_cell_content(self, player: Player) -> Any:
        if player.optional_single_tournament_player:
            return player.optional_single_tournament_player.rating
        else:
            return 0

    def update_from_used_columns(self, used_columns: list['DatasheetColumn']):
        for column in used_columns:
            if isinstance(column, TypedRatingColumn):
                self.is_informative = True
                return

    def augment_stored_player_with_tournament(
        self, tournament: Tournament | None, stored_player: StoredPlayer, value: str
    ):
        if not value:
            return
        if not value.isdigit() or (int_value := int(value)) == 0:
            raise SharlyChessException(_('A positive integer is expected.'))
        rating = PlayerRating(int_value, int_value, int_value)
        rating_bucket = (
            tournament.rating.value
            if tournament is not None
            else TournamentRating.STANDARD.value
        )
        stored_player.ratings[rating_bucket] = rating.stored_value

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        pass

    def check_data_source_value_match(self, value: str, player: Player) -> bool:
        return True


class RatingTypeColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'rating_type'

    def get_cell_content(self, player: Player) -> Any:
        if player.optional_single_tournament_player:
            return player.optional_single_tournament_player.rating_type.key.upper()
        else:
            return ''

    def update_from_used_columns(self, used_columns: list['DatasheetColumn']):
        for column in used_columns:
            if isinstance(column, TypedRatingColumn):
                self.is_informative = True
                return

    def augment_stored_player_with_tournament(
        self, tournament: Tournament | None, stored_player: StoredPlayer, value: str
    ):
        try:
            rating_type = PlayerRatingType.from_key(value)
        except ValueError:
            rating_type = PlayerRatingType.ESTIMATED
        rating_bucket = (
            tournament.rating.value
            if tournament is not None
            else TournamentRating.STANDARD.value
        )
        rating = PlayerRating.from_stored_value(
            stored_player.ratings.get(rating_bucket, {})
        )
        for type_ in PlayerRatingType:
            if type_ != rating_type:
                rating.set_value_from_type(None, rating_type)
        stored_player.ratings[rating_bucket] = rating.stored_value

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        pass

    def check_data_source_value_match(self, value: str, player: Player) -> bool:
        return True


class TypedRatingColumn(DatasheetColumn):
    def __init__(
        self, tournament_type: TournamentRating, rating_type: PlayerRatingType
    ):
        super().__init__()
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
            raise SharlyChessException(_('A positive integer is expected.'))
        rating = PlayerRating.from_stored_value(
            stored_player.ratings.get(self.tournament_type.value, {})
        )
        rating.set_value_from_type(int(value), self.rating_type)
        stored_player.ratings[self.tournament_type.value] = rating.stored_value
