"""A file grouping all the "utility" enum"""

from enum import Enum, StrEnum, IntEnum, auto, nonmember
from math import ceil
from typing import Iterator, Self, TYPE_CHECKING

from common.i18n import _
from utils import Utils

if TYPE_CHECKING:
    from data.player import TournamentPlayer
    from data.tournament import Tournament


class Result(IntEnum):
    """An enum representing the results in the database. Should be subclassed if the point value is not the default."""

    NO_RESULT = 0  # NOT PAIRED or NO RESULT YET
    LOSS = 1
    DRAW = 2
    WIN = 3
    FORFEIT_LOSS = 4
    DOUBLE_FORFEIT = 5
    FORFEIT_WIN = 6
    ZERO_POINT_BYE = 7
    HALF_POINT_BYE = 8
    PAIRING_ALLOCATED_BYE = 9
    FULL_POINT_BYE = 10
    UNRATED_LOSS = 11
    UNRATED_DRAW = 12
    UNRATED_WIN = 13
    REST_GAME = 14

    PENALTY_LL = 15  # 0-0
    PENALTY_DL = 16  # 0.5-0
    PENALTY_LD = 17  # 0-0.5
    UNRATED_PENALTY_LL = 18  # 0-0
    UNRATED_PENALTY_DL = 19  # 0.5-0
    UNRATED_PENALTY_LD = 20  # 0-0.5

    def __str__(self) -> str:
        match self:
            case Result.WIN:
                return '1-0'
            case Result.LOSS:
                return '0-1'
            case Result.DRAW:
                return '½-½'
            case Result.HALF_POINT_BYE:
                return '½-F'
            case Result.NO_RESULT | Result.ZERO_POINT_BYE:
                return ''
            case Result.FORFEIT_LOSS:
                return 'F-1'
            case (
                Result.FORFEIT_WIN
                | Result.PAIRING_ALLOCATED_BYE
                | Result.FULL_POINT_BYE
            ):
                return '1-F'
            case Result.DOUBLE_FORFEIT:
                return 'F-F'
            case Result.REST_GAME:
                return '0-F'
            case Result.UNRATED_WIN:
                return '1-0 (U)'
            case Result.UNRATED_LOSS:
                return '0-1 (U)'
            case Result.UNRATED_DRAW:
                return '½-½ (U)'
            case Result.PENALTY_LL:
                return '0-0'
            case Result.UNRATED_PENALTY_LL:
                return '0-0 (U)'
            case Result.PENALTY_DL:
                return '½-0'
            case Result.UNRATED_PENALTY_DL:
                return '½-0 (U)'
            case Result.PENALTY_LD:
                return '0-½'
            case Result.UNRATED_PENALTY_LD:
                return '0-½ (U)'
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def point_value(self) -> float:
        """
        The default value in points, according to FIDE rules, with a
        full-point Pairing Allocated Bye.
        Assumes a 0-0.5-1 scoring system.
        """
        match self:
            case (
                Result.NO_RESULT
                | Result.ZERO_POINT_BYE
                | Result.LOSS
                | Result.UNRATED_LOSS
                | Result.FORFEIT_LOSS
                | Result.DOUBLE_FORFEIT
                | Result.REST_GAME
                | Result.PENALTY_LL
                | Result.UNRATED_PENALTY_LL
                | Result.PENALTY_LD
                | Result.UNRATED_PENALTY_LD
            ):
                return 0.0
            case (
                Result.DRAW
                | Result.UNRATED_DRAW
                | Result.HALF_POINT_BYE
                | Result.PENALTY_DL
                | Result.UNRATED_PENALTY_DL
            ):
                return 0.5
            case (
                Result.WIN
                | Result.UNRATED_WIN
                | Result.FORFEIT_WIN
                | Result.PAIRING_ALLOCATED_BYE
                | Result.FULL_POINT_BYE
            ):
                return 1.0
            case _:
                raise ValueError(f'{self=}')

    def points(self, values: dict['Result', float] | None = None) -> float:
        """
        The value in points, according to rules defined in *values*.
        If a result instance is not included in *values*, the closest result's
        value will be used (e.g. `Result.PAIRING_ALLOCATED_BYE` will default to `Result.WIN`'s value)
        If the closest result's value is not given, will default to the default
        value, as defined by FIDE rules (1-0.5-0)
        """
        if not values:
            return self.point_value
        value = values.get(self)
        if value is not None:
            return value
        match self:
            case Result.DOUBLE_FORFEIT:
                value = values.get(Result.FORFEIT_LOSS, values.get(Result.LOSS))
            case (
                Result.FORFEIT_LOSS
                | Result.UNRATED_LOSS
                | Result.NO_RESULT
                | Result.ZERO_POINT_BYE
                | Result.PENALTY_LL
                | Result.UNRATED_PENALTY_LL
                | Result.PENALTY_LD
                | Result.UNRATED_PENALTY_LD
            ):
                value = values.get(Result.LOSS)
            case (
                Result.UNRATED_DRAW
                | Result.HALF_POINT_BYE
                | Result.PENALTY_DL
                | Result.UNRATED_PENALTY_DL
            ):
                value = values.get(Result.DRAW)
            case (
                Result.FULL_POINT_BYE
                | Result.FORFEIT_WIN
                | Result.UNRATED_WIN
                | Result.PAIRING_ALLOCATED_BYE
            ):
                value = values.get(Result.WIN)
        return value or self.point_value

    @property
    def opposite_result(self) -> 'Result':
        """Given a `Result` instance (white result), returns the result of the
        opponent.

        >>> Result.WIN.opposite_result == Result.LOSS
        True

        >>> Result.LOSS.opposite_result == Result.WIN
        True

        >>> Result.DRAW.opposite_result == Result.DRAW
        True

        >>> Result.NO_RESULT.opposite_result == Result.NO_RESULT
        True

        >>> Result.DOUBLE_FORFEIT.opposite_result == Result.DOUBLE_FORFEIT
        True
        """
        match self:
            case Result.LOSS:
                return Result.WIN
            case Result.WIN:
                return Result.LOSS
            case Result.DRAW:
                return Result.DRAW
            case Result.UNRATED_LOSS:
                return Result.UNRATED_WIN
            case Result.UNRATED_WIN:
                return Result.UNRATED_LOSS
            case Result.UNRATED_DRAW:
                return Result.UNRATED_DRAW
            case Result.FORFEIT_WIN:
                return Result.FORFEIT_LOSS
            case Result.FORFEIT_LOSS:
                return Result.FORFEIT_WIN
            case Result.DOUBLE_FORFEIT:
                return Result.DOUBLE_FORFEIT
            case Result.NO_RESULT:
                return Result.NO_RESULT
            case Result.PENALTY_LL:
                return Result.PENALTY_LL
            case Result.PENALTY_DL:
                return Result.PENALTY_LD
            case Result.PENALTY_LD:
                return Result.PENALTY_DL
            case Result.UNRATED_PENALTY_LL:
                return Result.UNRATED_PENALTY_LL
            case Result.UNRATED_PENALTY_DL:
                return Result.UNRATED_PENALTY_LD
            case Result.UNRATED_PENALTY_LD:
                return Result.UNRATED_PENALTY_DL
            case (
                Result.ZERO_POINT_BYE
                | Result.HALF_POINT_BYE
                | Result.PAIRING_ALLOCATED_BYE
                | Result.FULL_POINT_BYE
            ):
                raise ValueError(f"Result '{self}' is not reversible")
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def to_trf(self) -> str:
        from data.input_output.trf.trf_mappers import TrfResult

        return TrfResult.get_outer_value(self)

    @property
    def to_norm_report(self) -> str:
        from data.input_output.norm_mappers import NormResult

        return NormResult.get_outer_value(self)

    @property
    def to_crosstable(self) -> str:
        match self:
            case (
                Result.LOSS
                | Result.UNRATED_LOSS
                | Result.PENALTY_LL
                | Result.UNRATED_PENALTY_LL
            ):
                return '-'
            case (
                Result.DRAW
                | Result.UNRATED_DRAW
                | Result.HALF_POINT_BYE
                | Result.PENALTY_DL
                | Result.UNRATED_PENALTY_DL
            ):
                return '='
            case Result.WIN | Result.UNRATED_WIN:
                return '+'
            case Result.FORFEIT_LOSS | Result.DOUBLE_FORFEIT:
                return '<'
            case Result.FORFEIT_WIN | Result.FULL_POINT_BYE:
                return '>'
            case Result.PAIRING_ALLOCATED_BYE:
                return 'EXE'
            case Result.ZERO_POINT_BYE | Result.NO_RESULT | Result.REST_GAME:
                return ' '
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def to_berger_table(self) -> str:
        return self.to_trf

    @property
    def to_pgn(self) -> str:
        match self:
            case Result.WIN | Result.UNRATED_WIN:
                return '1-0'
            case Result.LOSS | Result.UNRATED_LOSS:
                return '0-1'
            case Result.DRAW | Result.UNRATED_DRAW:
                return '1/2-1/2'
            case (
                Result.NO_RESULT
                | Result.FORFEIT_WIN
                | Result.FORFEIT_LOSS
                | Result.FULL_POINT_BYE
                | Result.HALF_POINT_BYE
                | Result.ZERO_POINT_BYE
                | Result.PAIRING_ALLOCATED_BYE
                | Result.REST_GAME
                | Result.PENALTY_LL
                | Result.UNRATED_PENALTY_LL
                | Result.PENALTY_LD
                | Result.UNRATED_PENALTY_LD
            ):
                return '*'
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def bbp_field(self) -> str:
        match self:
            case Result.LOSS:
                return 'BBL'
            case Result.DRAW:
                return 'BBD'
            case Result.WIN:
                return 'BBW'
            case Result.FORFEIT_LOSS:
                return 'BBF'
            case Result.PAIRING_ALLOCATED_BYE:
                return 'BBU'
            case Result.ZERO_POINT_BYE:
                return 'BBZ'
            case _:
                raise ValueError(f'Result with no matching BBP field: {self}')

    @property
    def is_win(self) -> bool:
        return self in (
            Result.WIN,
            Result.UNRATED_WIN,
        )

    @property
    def is_draw(self) -> bool:
        return self in (
            Result.DRAW,
            Result.UNRATED_DRAW,
            Result.PENALTY_DL,
            Result.UNRATED_PENALTY_DL,
        )

    @property
    def is_unrated_draw(self) -> bool:
        return self in (
            Result.UNRATED_DRAW,
            Result.UNRATED_PENALTY_DL,
        )

    @property
    def is_loss(self) -> bool:
        return self in (
            Result.LOSS,
            Result.UNRATED_LOSS,
            Result.PENALTY_LL,
            Result.PENALTY_LD,
            Result.UNRATED_PENALTY_LL,
            Result.UNRATED_PENALTY_LD,
        )

    @property
    def is_unrated_loss(self) -> bool:
        return self in (
            Result.UNRATED_LOSS,
            Result.UNRATED_PENALTY_LL,
            Result.UNRATED_PENALTY_LD,
        )

    @property
    def is_bye(self) -> bool:
        return self.is_no_board_bye or self.is_board_bye

    @property
    def is_board_bye(self) -> bool:
        return self in (
            Result.PAIRING_ALLOCATED_BYE,
            Result.REST_GAME,
        )

    @property
    def is_no_board_bye(self) -> bool:
        return self in (
            Result.ZERO_POINT_BYE,
            Result.HALF_POINT_BYE,
            Result.FULL_POINT_BYE,
        )

    @property
    def is_next_round_bye(self) -> bool:
        return self in (
            Result.ZERO_POINT_BYE,
            Result.HALF_POINT_BYE,
            Result.FULL_POINT_BYE,
        )

    @property
    def is_requested_bye(self) -> bool:
        return self in (
            Result.ZERO_POINT_BYE,
            Result.HALF_POINT_BYE,
        )

    @property
    def is_unplayed(self) -> bool:
        return self in (
            Result.NO_RESULT,
            Result.FORFEIT_WIN,
            Result.FORFEIT_LOSS,
            Result.DOUBLE_FORFEIT,
            Result.HALF_POINT_BYE,
            Result.ZERO_POINT_BYE,
            Result.FULL_POINT_BYE,
            Result.PAIRING_ALLOCATED_BYE,
            Result.REST_GAME,
        )

    @property
    def is_voluntary_unplayed(self) -> bool:
        return self in (
            Result.FORFEIT_LOSS,
            Result.DOUBLE_FORFEIT,
            Result.HALF_POINT_BYE,
            Result.ZERO_POINT_BYE,
        )

    @property
    def is_special_result(self) -> bool:
        """Unusual results that my need permission to be entered."""
        return self in (
            Result.UNRATED_LOSS,
            Result.UNRATED_DRAW,
            Result.UNRATED_WIN,
            Result.PENALTY_LL,
            Result.PENALTY_DL,
            Result.PENALTY_LD,
            Result.UNRATED_PENALTY_LL,
            Result.UNRATED_PENALTY_DL,
            Result.UNRATED_PENALTY_LD,
        )

    @classmethod
    def user_imputable_results(cls) -> tuple['Result', ...]:
        """Imputable results are the ones that a player can
        input by themselves, namely a win, a draw, or a loss or forfeits."""
        return cls.WIN, cls.DRAW, cls.LOSS

    @classmethod
    def admin_imputable_results(cls) -> tuple['Result', ...]:
        """Admin imputable results are the ones that only arbiters can input."""
        return cls.user_imputable_results() + (
            cls.NO_RESULT,
            cls.FORFEIT_WIN,
            cls.FORFEIT_LOSS,
            cls.DOUBLE_FORFEIT,
            cls.UNRATED_LOSS,
            cls.UNRATED_DRAW,
            cls.UNRATED_WIN,
            cls.PENALTY_LL,
            cls.PENALTY_DL,
            cls.PENALTY_LD,
            cls.UNRATED_PENALTY_LL,
            cls.UNRATED_PENALTY_DL,
            cls.UNRATED_PENALTY_LD,
        )


class TournamentRating(IntEnum):
    """A wrapper around the tournament rating type."""

    STANDARD = 1
    RAPID = 2
    BLITZ = 3

    @classmethod
    def from_key(cls, key: str) -> Self:
        match key.lower():
            case 'standard':
                return cls.STANDARD
            case 'rapid':
                return cls.RAPID
            case 'blitz':
                return cls.BLITZ
            case _:
                raise ValueError(f'Unknown value: {key}')

    @property
    def form_key(self) -> str:
        match self:
            case TournamentRating.STANDARD:
                return 'standard'
            case TournamentRating.RAPID:
                return 'rapid'
            case TournamentRating.BLITZ:
                return 'blitz'
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def print_view_header(self) -> str:
        match self:
            case TournamentRating.STANDARD:
                return _('Elo *** STD ELO COLUMN HEADER')
            case TournamentRating.RAPID:
                return _('Rapid *** RAPID ELO COLUMN HEADER')
            case TournamentRating.BLITZ:
                return _('Blitz *** BLITZ ELO COLUMN HEADER')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def name(self) -> str:
        match self:
            case TournamentRating.STANDARD:
                return _('Standard rating')
            case TournamentRating.RAPID:
                return _('Rapid rating')
            case TournamentRating.BLITZ:
                return _('Blitz rating')
            case _:
                raise ValueError(f'Unknown rating: {self}')

    @property
    def short_name(self) -> str:
        match self:
            case TournamentRating.STANDARD:
                return _('Standard')
            case TournamentRating.RAPID:
                return _('Rapid')
            case TournamentRating.BLITZ:
                return _('Blitz')
            case _:
                raise ValueError(f'Unknown rating: {self}')

    @property
    def acronym(self) -> str:
        match self:
            case TournamentRating.STANDARD:
                return _('Std *** STANDARD RATING ACRONYM')
            case TournamentRating.RAPID:
                return _('Rpd *** RAPID RATING ACRONYM')
            case TournamentRating.BLITZ:
                return _('Blz *** BLITZ RATING ACRONYM')
            case _:
                raise ValueError(f'Unknown rating: {self}')

    def __str__(self) -> str:
        return self.name


class PlayerGender(StrEnum):
    NONE = ''
    WOMAN = 'F'  # Kept as 'F' for compatibility reasons
    MAN = 'M'

    @classmethod
    def from_fide_value(cls, value: str) -> 'PlayerGender':
        match value.upper():
            case 'F' | 'W':
                return cls.WOMAN
            case 'M':
                return cls.MAN
            case _:
                raise ValueError(f'Unknown value: {value}')

    @property
    def key(self) -> str:
        if self == self.WOMAN:
            return 'W'
        return self.value

    @classmethod
    def from_key(cls, key: str) -> Self:
        match key.upper():
            case 'F' | 'W':
                return cls.WOMAN
            case 'M':
                return cls.MAN
            case '' | ' ':
                return cls.NONE
            case _:
                raise ValueError(f'Unknown value: {key}')

    @property
    def name(self) -> str:
        match self:
            case PlayerGender.NONE:
                return _('- *** NAME FOR GENDER NONE')
            case PlayerGender.WOMAN:
                return _('Woman *** NAME FOR GENDER WOMAN')
            case PlayerGender.MAN:
                return _('Man *** NAME FOR GENDER MAN')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def short_name(self) -> str:
        match self:
            case PlayerGender.NONE:
                return _('- *** SHORT NAME FOR GENDER NONE')
            case PlayerGender.WOMAN:
                return _('W *** SHORT NAME FOR GENDER WOMAN')
            case PlayerGender.MAN:
                return _('M *** SHORT NAME FOR GENDER MAN')
            case _:
                raise ValueError(f'Unknown value: {self}')


class PlayerRatingType(IntEnum):
    ESTIMATED = 1
    NATIONAL = 2
    FIDE = 3

    @property
    def name(self) -> str:
        match self:
            case PlayerRatingType.ESTIMATED:
                return _('Estimated *** NAME FOR RATING TYPE ESTIMATED')
            case PlayerRatingType.NATIONAL:
                return _('National *** NAME FOR RATING TYPE NATIONAL')
            case PlayerRatingType.FIDE:
                return _('FIDE *** NAME FOR RATING TYPE FIDE')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def short_name(self) -> str:
        match self:
            case PlayerRatingType.ESTIMATED:
                return _('E *** SHORT NAME FOR RATING TYPE ESTIMATED')
            case PlayerRatingType.NATIONAL:
                return _('N *** SHORT NAME FOR RATING TYPE NATIONAL')
            case PlayerRatingType.FIDE:
                return _('F *** SHORT NAME FOR RATING TYPE FIDE')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def key(self) -> str:
        match self:
            case PlayerRatingType.ESTIMATED:
                return 'e'
            case PlayerRatingType.NATIONAL:
                return 'n'
            case PlayerRatingType.FIDE:
                return 'f'
            case _:
                raise ValueError(f'Unknown value: {self}')

    @classmethod
    def from_key(cls, key: str) -> Self:
        match key.lower():
            case 'e':
                return PlayerRatingType.ESTIMATED
            case 'n':
                return PlayerRatingType.NATIONAL
            case 'f':
                return PlayerRatingType.FIDE
            case _:
                raise ValueError(f'Unknown value: {key}')

    def __str__(self) -> str:
        return self.short_name


class PlayerTitle(StrEnum):
    """The possible FIDE player titles: GM, WGM, IM, WIM, FM, WFM, CM, WCM.
    Also includes the "no title" case."""

    NONE = ''
    WOMAN_CANDIDATE_MASTER = 'WCM'
    CANDIDATE_MASTER = 'CM'
    WOMAN_FIDE_MASTER = 'WFM'
    FIDE_MASTER = 'FM'
    WOMAN_INTERNATIONAL_MASTER = 'WIM'
    INTERNATIONAL_MASTER = 'IM'
    WOMAN_GRANDMASTER = 'WGM'
    GRANDMASTER = 'GM'

    @property
    def sort_index(self) -> int:
        if self == self.NONE:
            return 0
        return list(PlayerTitle).index(self)

    @classmethod
    def from_fide_value(cls, value: str) -> 'PlayerTitle':
        try:
            return cls(value)
        except ValueError:
            return cls.NONE

    @property
    def name(self) -> str:
        match self:
            case PlayerTitle.NONE:
                return '-'
            case PlayerTitle.WOMAN_CANDIDATE_MASTER:
                return _('Woman Candidate Master')
            case PlayerTitle.CANDIDATE_MASTER:
                return _('Candidate Master')
            case PlayerTitle.WOMAN_FIDE_MASTER:
                return _('Woman Fide Master')
            case PlayerTitle.FIDE_MASTER:
                return _('Fide Master')
            case PlayerTitle.WOMAN_INTERNATIONAL_MASTER:
                return _('Woman International Master')
            case PlayerTitle.INTERNATIONAL_MASTER:
                return _('International Master')
            case PlayerTitle.WOMAN_GRANDMASTER:
                return _('Woman Grand Master')
            case PlayerTitle.GRANDMASTER:
                return _('Grand Master')
            case _:
                raise ValueError(f'Unknown title: {self}')

    @property
    def short_name(self) -> str:
        match self:
            case PlayerTitle.NONE:
                return ''
            case PlayerTitle.WOMAN_CANDIDATE_MASTER:
                return _('WCM *** SHORT NAME FOR Woman Candidate Master')
            case PlayerTitle.CANDIDATE_MASTER:
                return _('CM *** SHORT NAME FOR Candidate Master')
            case PlayerTitle.WOMAN_FIDE_MASTER:
                return _('WFM *** SHORT NAME FOR Woman Fide Master')
            case PlayerTitle.FIDE_MASTER:
                return _('FM *** SHORT NAME FOR Fide Master')
            case PlayerTitle.WOMAN_INTERNATIONAL_MASTER:
                return _('WIM *** SHORT NAME FOR Woman International Master')
            case PlayerTitle.INTERNATIONAL_MASTER:
                return _('IM *** SHORT NAME FOR International Master')
            case PlayerTitle.WOMAN_GRANDMASTER:
                return _('WGM *** SHORT NAME FOR Woman Grand Master')
            case PlayerTitle.GRANDMASTER:
                return _('GM *** SHORT NAME FOR Grand Master')
            case _:
                raise ValueError(f'Unknown title: {self}')

    def __str__(self) -> str:
        return self.short_name


class FideArbiterTitle(StrEnum):
    """The possible FIDE arbiter titles: IA, FA, NA.
    Also includes the "no title" case."""

    NONE = ''
    NATIONAL = 'NA'
    FIDE = 'FA'
    INTERNATIONAL = 'IA'

    @property
    def sort_index(self) -> int:
        if self == self.NONE:
            return 0
        return list(FideArbiterTitle).index(self)

    @classmethod
    def from_fide_value(cls, value: str) -> 'FideArbiterTitle':
        for string in value.split(','):
            match string:
                case 'NA':
                    return FideArbiterTitle.NATIONAL
                case 'FA':
                    return FideArbiterTitle.FIDE
                case 'IA':
                    return FideArbiterTitle.INTERNATIONAL
        return FideArbiterTitle.NONE

    @property
    def name(self) -> str:
        match self:
            case FideArbiterTitle.NONE:
                return '-'
            case FideArbiterTitle.NATIONAL:
                return _('National Arbiter')
            case FideArbiterTitle.FIDE:
                return _('FIDE Arbiter')
            case FideArbiterTitle.INTERNATIONAL:
                return _('International Arbiter')
            case _:
                raise ValueError(f'Unknown title: {self}')

    @property
    def short_name(self) -> str:
        match self:
            case FideArbiterTitle.NONE:
                return ''
            case FideArbiterTitle.NATIONAL:
                return _('NA *** SHORT NAME FOR National Arbiter')
            case FideArbiterTitle.FIDE:
                return _('FA *** SHORT NAME FOR FIDE Arbiter')
            case FideArbiterTitle.INTERNATIONAL:
                return _('IA *** SHORT NAME FOR International Arbiter')
            case _:
                raise ValueError(f'Unknown title: {self}')

    @property
    def fide_acronym(self) -> str:
        return self.value


class RoleType(StrEnum):
    CHIEF_ARBITER = 'chief_arbiter'
    DEPUTY_ARBITER = 'deputy_arbiter'
    ORGANISER = 'organiser'

    @property
    def is_tournament_bound(self) -> bool:
        return self is not RoleType.ORGANISER

    @property
    def sort_order(self) -> int:
        """Defines display / logical order for roles."""
        order_map = {
            RoleType.CHIEF_ARBITER: 0,
            RoleType.DEPUTY_ARBITER: 1,
            RoleType.ORGANISER: 2,
        }
        return order_map[self]

    def __str__(self):
        match self:
            case RoleType.CHIEF_ARBITER:
                return _('Chief arbiter')
            case RoleType.DEPUTY_ARBITER:
                return _('Deputy arbiter')
            case RoleType.ORGANISER:
                return _('Organiser')
            case _:
                raise ValueError(f'Unknown value: {self}')


class TitleNorm(Enum):
    WIM = auto()
    WGM = auto()
    IM = auto()
    GM = auto()

    @classmethod
    def values(cls) -> Iterator['TitleNorm']:
        yield cls.WIM
        yield cls.WGM
        yield cls.IM
        yield cls.GM

    @property
    def player_title(self) -> PlayerTitle:
        match self:
            case TitleNorm.WIM:
                return PlayerTitle.WOMAN_INTERNATIONAL_MASTER
            case TitleNorm.WGM:
                return PlayerTitle.WOMAN_GRANDMASTER
            case TitleNorm.IM:
                return PlayerTitle.INTERNATIONAL_MASTER
            case TitleNorm.GM:
                return PlayerTitle.GRANDMASTER
            case _:
                raise AssertionError(f'unhandled TitleNorm: {self!r}')

    def satisfies_gender_requirement(self, gender: PlayerGender) -> bool:
        match self:
            case TitleNorm.WIM | TitleNorm.WGM:
                return gender == PlayerGender.WOMAN
            case _:
                return True

    @property
    def minimum_rating(self) -> int:
        match self:
            case TitleNorm.WIM:
                return 1850
            case TitleNorm.WGM:
                return 2000
            case TitleNorm.IM:
                return 2050
            case TitleNorm.GM:
                return 2200
            case _:
                raise ValueError(f'Invalid title norm value: {self}')

    @property
    def minimum_average(self) -> int:
        match self:
            case TitleNorm.WIM:
                return 2030
            case TitleNorm.WGM:
                return 2180
            case TitleNorm.IM:
                return 2230
            case TitleNorm.GM:
                return 2380
            case _:
                raise ValueError(f'Invalid title norm value: {self}')

    @property
    def minimum_performance(self) -> float:
        match self:
            case TitleNorm.WIM:
                return 2250
            case TitleNorm.WGM:
                return 2400
            case TitleNorm.IM:
                return 2450
            case TitleNorm.GM:
                return 2600
            case _:
                raise ValueError(f'Invalid title norm value: {self}')

    @staticmethod
    def minimum_rounds(tournament: 'Tournament') -> int:
        from data.pairings.variations import DoubleBergerRoundRobinVariation

        if tournament.pairing_variation == DoubleBergerRoundRobinVariation():
            return 10  # 1.4.5.f -> 6 players -> 10 rounds
        return 9

    @staticmethod
    def minimum_score(rounds: int) -> float:
        return Result.WIN.points() * 0.35 * rounds

    @staticmethod
    def minimum_title_holders(rounds: int) -> int:
        return ceil(rounds / 2)

    @staticmethod
    def minimum_required_titles(tournament: 'Tournament', played_games: int) -> int:
        """1.4.5b–e: "at least 1/3 of the opponents, minimum 3" (or 1/2 in DRR).

        Threshold scales with the size of the opponent mix (`played_games`),
        not the tournament's nominal round count — see 1.4.1c which says
        the mix requirements apply to the actually-played opponents.
        """
        from data.pairings.variations import DoubleBergerRoundRobinVariation

        if tournament.pairing_variation == DoubleBergerRoundRobinVariation():
            return ceil(played_games / 2)  # 1.4.5.f
        return max(ceil(played_games / 3), 3)

    @staticmethod
    def maximum_of_own_federation(rounds: int) -> int:
        return (3 * rounds) // 5

    @staticmethod
    def maximum_of_one_federation(rounds: int) -> int:
        return (2 * rounds) // 3

    # 1.4.5a — titles that count as "title-holders" for the 50% rule.
    # CM and WCM are explicitly excluded by the spec. Same set for every norm.
    # `nonmember` stops Enum's metaclass from turning the tuple into a member.
    TITLE_HOLDERS = nonmember(
        (
            PlayerTitle.WOMAN_FIDE_MASTER,
            PlayerTitle.FIDE_MASTER,
            PlayerTitle.WOMAN_INTERNATIONAL_MASTER,
            PlayerTitle.INTERNATIONAL_MASTER,
            PlayerTitle.WOMAN_GRANDMASTER,
            PlayerTitle.GRANDMASTER,
        )
    )

    # 1.4.3d — the Swiss-exception's "titleholder" subset excludes FM/WFM.
    # Spec wording: "at least 10 GM/IM/WGM/WIM titleholders" (narrower than
    # 1.4.5a's title-holder set).
    MASTER_TITLES = nonmember(
        (
            PlayerTitle.WOMAN_INTERNATIONAL_MASTER,
            PlayerTitle.INTERNATIONAL_MASTER,
            PlayerTitle.WOMAN_GRANDMASTER,
            PlayerTitle.GRANDMASTER,
        )
    )

    @property
    def required_titles(self) -> tuple[PlayerTitle, ...]:
        match self:
            case TitleNorm.WIM:
                return (
                    PlayerTitle.WOMAN_INTERNATIONAL_MASTER,
                    PlayerTitle.WOMAN_GRANDMASTER,
                    PlayerTitle.INTERNATIONAL_MASTER,
                    PlayerTitle.GRANDMASTER,
                )
            case TitleNorm.WGM:
                return (
                    PlayerTitle.WOMAN_GRANDMASTER,
                    PlayerTitle.INTERNATIONAL_MASTER,
                    PlayerTitle.GRANDMASTER,
                )
            case TitleNorm.IM:
                return (
                    PlayerTitle.INTERNATIONAL_MASTER,
                    PlayerTitle.GRANDMASTER,
                )
            case TitleNorm.GM:
                return (PlayerTitle.GRANDMASTER,)


class BoardColor(StrEnum):
    WHITE = 'W'
    BLACK = 'B'

    @property
    def to_crosstable(self) -> str:
        match self:
            case BoardColor.WHITE:
                return _('W *** WHITE COLOR FOR CROSSTABLE')
            case BoardColor.BLACK:
                return _('B *** BLACK COLOR FOR CROSSTABLE')
            case _:
                raise ValueError(f'Unknown value:  {self}')

    @property
    def name(self) -> str:
        match self:
            case BoardColor.WHITE:
                return _('White')
            case BoardColor.BLACK:
                return _('Black')
            case _:
                raise ValueError(f'Unknown value: {self}')

    def __str__(self) -> str:
        return self.name


class ScreenType(StrEnum):
    CHECK_IN = 'check-in'
    INPUT = 'input'
    BOARDS = 'boards'
    PLAYERS = 'players'
    RESULTS = 'results'
    RANKING = 'ranking'
    IMAGE = 'image'

    @classmethod
    def screen_types(cls) -> tuple[Self, ...]:
        return tuple(cls(st) for st in cls)

    @property
    def name(self) -> str:
        match self:
            case ScreenType.BOARDS:
                return _('Pairings by board')
            case ScreenType.CHECK_IN:
                return _('Check-in')
            case ScreenType.INPUT:
                return _('Results entry')
            case ScreenType.PLAYERS:
                return _('Pairings by player')
            case ScreenType.RESULTS:
                return _('Last results')
            case ScreenType.RANKING:
                return _('Ranking')
            case ScreenType.IMAGE:
                return _('Image')
            case _:
                raise ValueError(f'Invalid screen type: {self}')

    def __str__(self) -> str:
        return self.name

    @property
    def icon_str(self) -> str:
        match self:
            case self.BOARDS:
                return 'bi-card-list'
            case self.CHECK_IN:
                return 'bi-check-square'
            case self.INPUT:
                return 'bi-pencil'
            case self.PLAYERS:
                return 'bi-people'
            case self.RESULTS:
                return 'bi-1-square'
            case self.RANKING:
                return 'bi-trophy'
            case self.IMAGE:
                return 'bi-image'
            case _:
                raise ValueError(f'Invalid screen type: {self}')

    @property
    def tooltip_text(self) -> str:
        match self:
            case self.BOARDS:
                return _('Boards screens show pairings by board number.')
            case self.CHECK_IN:
                return _('Check-in screens allow players to check-in or out.')
            case self.INPUT:
                return _(
                    'Input screens show pairings by board number and allow people to enter results.'
                )
            case self.PLAYERS:
                return _('Players screens show pairings by alphabetical order.')
            case self.RESULTS:
                return _('Results screens show the last results (most recent first).')
            case self.RANKING:
                return _('Ranking screens show the players by rank.')
            case self.IMAGE:
                return _('Image screens show an image (local or remote).')
            case _:
                raise ValueError(f'Invalid screen type: {self}')

    @property
    def families_allowed(self) -> bool:
        """Returns True if the screen type can be used for families, False otherwise."""
        match self:
            case self.BOARDS | self.INPUT | self.PLAYERS | self.RANKING | self.CHECK_IN:
                return True
            case self.RESULTS | self.IMAGE:
                return False
            case _:
                raise ValueError(f'Invalid screen type: {self}')


class PlayersScreenPlayerFormat(IntEnum):
    NAME = 1
    NAME_RATING = 2
    NAME_RATING_TYPE = 3
    NAME_RATING_TYPE_POINTS = 4

    @property
    def format_string(self) -> str:
        match self:
            case PlayersScreenPlayerFormat.NAME:
                return _('{title} {full_name}')
            case PlayersScreenPlayerFormat.NAME_RATING:
                return _('{title} {full_name} {rating}')
            case PlayersScreenPlayerFormat.NAME_RATING_TYPE:
                return _('{title} {full_name} {rating}{rating_type}')
            case PlayersScreenPlayerFormat.NAME_RATING_TYPE_POINTS:
                return _('{title} {full_name} {rating}{rating_type} [{points}]')
            case _:
                raise ValueError(f'Unknown value: {self}')

    def header(
        self,
        tournament: 'Tournament',
    ) -> str:
        match self:
            case PlayersScreenPlayerFormat.NAME:
                return _('Player')
            case PlayersScreenPlayerFormat.NAME_RATING:
                return _('Player Elo')
            case PlayersScreenPlayerFormat.NAME_RATING_TYPE:
                return _('Player Elo')
            case PlayersScreenPlayerFormat.NAME_RATING_TYPE_POINTS:
                return (
                    _('Player Elo [Pts]')
                    if tournament.current_round
                    else _('Player Elo')
                )
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def example(self) -> str:
        from data.player import TournamentPlayer

        return self.format_string.format(
            title=PlayerTitle.GRANDMASTER,
            full_name=TournamentPlayer.player_full_name(
                first_name='Magnus', last_name='CARLSEN'
            ),
            rating=2840,
            rating_type=PlayerRatingType.FIDE,
            points=4,
        )

    def format(
        self,
        player: 'TournamentPlayer',
    ) -> str:
        return self.format_string.format(
            title=player.title.short_name,
            full_name=player.full_name,
            rating=player.rating,
            rating_type=player.rating_type.short_name,
            points=Utils.points_str(player.vpoints),
        )


class PlayersScreenBoardFormat(IntEnum):
    MINIMAL = 1
    MEDIUM_1 = 2
    MEDIUM_2 = 3
    FULL = 4

    @property
    def format_string(self) -> str:
        match self:
            case PlayersScreenBoardFormat.MINIMAL:
                return _('{board_number} {color}')
            case PlayersScreenBoardFormat.MEDIUM_1:
                return _('#{board_number} with {color}')
            case PlayersScreenBoardFormat.MEDIUM_2:
                return _('Board #{board_number} {color}')
            case PlayersScreenBoardFormat.FULL:
                return _('Board #{board_number} with {color}')
            case _:
                raise ValueError(f'Unknown value: {self}')

    def header(
        self,
        tournament: 'Tournament',
    ) -> str:
        if not tournament.current_round:
            return ''
        match self:
            case PlayersScreenBoardFormat.MINIMAL:
                return _('Board')
            case (
                PlayersScreenBoardFormat.MEDIUM_1
                | PlayersScreenBoardFormat.MEDIUM_2
                | PlayersScreenBoardFormat.FULL
            ):
                return _('Board and Color')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def example(self) -> str:
        return self.format_string.format(
            board_number='27',
            color=_('White'),
        )

    def format(
        self,
        tournament_player: 'TournamentPlayer',
    ) -> str:
        return self.format_string.format(
            board_number=tournament_player.board_number,
            color=tournament_player.color_str,
        )


class PlayersScreenOpponentFormat(IntEnum):
    NONE = 1
    NAME = 2
    NAME_RATING = 3
    NAME_RATING_TYPE = 4
    NAME_RATING_TYPE_POINTS = 5

    @property
    def format_string(self) -> str:
        match self:
            case PlayersScreenOpponentFormat.NONE:
                return ''
            case PlayersScreenOpponentFormat.NAME:
                return PlayersScreenPlayerFormat.NAME.format_string
            case PlayersScreenOpponentFormat.NAME_RATING:
                return PlayersScreenPlayerFormat.NAME_RATING.format_string
            case PlayersScreenOpponentFormat.NAME_RATING_TYPE:
                return PlayersScreenPlayerFormat.NAME_RATING_TYPE.format_string
            case PlayersScreenOpponentFormat.NAME_RATING_TYPE_POINTS:
                return PlayersScreenPlayerFormat.NAME_RATING_TYPE_POINTS.format_string
            case _:
                raise ValueError(f'Unknown value: {self}')

    def header(
        self,
        tournament: 'Tournament',
    ) -> str:
        match self:
            case PlayersScreenOpponentFormat.NONE:
                return ''
            case PlayersScreenOpponentFormat.NAME:
                return _('Opponent')
            case PlayersScreenOpponentFormat.NAME_RATING:
                return _('Opponent Elo')
            case PlayersScreenOpponentFormat.NAME_RATING_TYPE:
                return _('Opponent Elo')
            case PlayersScreenOpponentFormat.NAME_RATING_TYPE_POINTS:
                return (
                    _('Opponent Elo [Pts]')
                    if tournament.current_round
                    else _('Opponent Elo')
                )
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def example(self) -> str:
        from data.player import TournamentPlayer

        return (
            self.format_string.format(
                title=PlayerTitle.GRANDMASTER,
                full_name=TournamentPlayer.player_full_name(
                    first_name='Yifan', last_name='HOU'
                ),
                rating=2613,
                rating_type=PlayerRatingType.FIDE,
                points=Utils.points_str(6),
            )
            or '-'
        )

    def format(
        self,
        tournament_player: 'TournamentPlayer',
    ) -> str:
        return self.format_string.format(
            title=tournament_player.title.short_name,
            full_name=tournament_player.full_name,
            rating=tournament_player.rating,
            rating_type=tournament_player.rating_type.short_name,
            points=tournament_player.vpoints_str,
        )


class NeedsUpload(Enum):
    YES = 0
    RECENT_CHANGE = 1
    NO_CHANGE = 2

    def __bool__(self):
        match self:
            case NeedsUpload.YES:
                return True
            case NeedsUpload.NO_CHANGE | NeedsUpload.RECENT_CHANGE:
                return False
            case _:
                raise ValueError(f'Unknown value: {self}')


class FormAction(StrEnum):
    UPDATE = 'update'
    CREATE = 'create'
    CLONE = 'clone'
    DELETE = 'delete'
    REPLACE = 'replace'


class CheckInStatus(IntEnum):
    WITHDRAWN = 0
    NEXT_ROUND_ZPB = 1
    NEXT_ROUND_HPB = 2
    NEXT_ROUND_FPB = 3
    ABSENT = 4
    PRESENT = 5
    NEXT_ROUND_BYE = 6

    @property
    def name(self) -> str:
        match self:
            case self.WITHDRAWN:
                return _('Withdrawn')
            case self.NEXT_ROUND_ZPB:
                return _('Zero-Point Bye')
            case self.NEXT_ROUND_HPB:
                return _('Half-Point Bye')
            case self.NEXT_ROUND_FPB:
                return _('Full-Point Bye')
            case self.NEXT_ROUND_BYE:
                return ''
            case self.PRESENT:
                return _('Present')
            case self.ABSENT:
                return _('Absent')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def description(self) -> str:
        match self:
            case self.WITHDRAWN:
                return _('Received a Zero-Point Bye for all the remaining rounds')
            case self.NEXT_ROUND_ZPB:
                return _('Received a Zero-Point Bye for the next round')
            case self.NEXT_ROUND_HPB:
                return _('Received a Half-Point Bye for the next round')
            case self.NEXT_ROUND_FPB:
                return _('Received a Full-Point Bye for the next round')
            case self.NEXT_ROUND_BYE:
                return ''
            case self.ABSENT:
                return _('Will not participate by default in upcoming rounds')
            case self.PRESENT:
                return _('Will participate in upcoming rounds')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def icon_classes(self) -> str:
        return self.base_icon_class + ' ' + self.color_icon_class

    @property
    def base_icon_class(self) -> str:
        match self:
            case self.WITHDRAWN:
                return 'bi-sign-stop'
            case self.NEXT_ROUND_ZPB:
                return 'bi-0-circle-fill'
            case self.NEXT_ROUND_HPB:
                return 'bi-circle-half'
            case self.NEXT_ROUND_FPB:
                return 'bi-1-circle-fill'
            case self.NEXT_ROUND_BYE:
                return ''
            case self.PRESENT:
                return 'bi-check-circle-fill'
            case self.ABSENT:
                return 'bi-x-circle-fill'
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def color_icon_class(self) -> str:
        if self == self.PRESENT:
            return 'text-success'
        if self == self.ABSENT:
            return 'text-danger'
        return 'text-body text-secondary'

    @property
    def is_next_round_bye(self) -> bool:
        return self not in (self.ABSENT, self.PRESENT)
