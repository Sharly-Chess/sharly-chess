"""A file grouping all the "utility" classes/enum"""

from datetime import date, datetime, timedelta
from enum import Enum, StrEnum, IntEnum
from typing import Self

from common.i18n import _


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
            case Result.DRAW | Result.HALF_POINT_BYE:
                return '½-½'
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
        if not isinstance(values, dict):
            return self.point_value
        value: float | None = values.get(self, None)
        if value is not None:
            return value
        match self:
            case Result.DOUBLE_FORFEIT:
                value = (
                    value or values.get(Result.FORFEIT_LOSS) or values.get(Result.LOSS)
                )
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
                value = value or values.get(Result.LOSS)
            case (
                Result.UNRATED_DRAW
                | Result.HALF_POINT_BYE
                | Result.PENALTY_DL
                | Result.UNRATED_PENALTY_DL
            ):
                value = value or values.get(Result.DRAW)
            case (
                Result.FULL_POINT_BYE
                | Result.FORFEIT_WIN
                | Result.UNRATED_WIN
                | Result.PAIRING_ALLOCATED_BYE
            ):
                value = value or values.get(Result.WIN)
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
        match self:
            case Result.LOSS | Result.PENALTY_LL | Result.PENALTY_LD:
                return '0'
            case Result.DRAW | Result.PENALTY_DL:
                return '='
            case Result.WIN:
                return '1'
            case (
                Result.UNRATED_LOSS
                | Result.UNRATED_PENALTY_LL
                | Result.UNRATED_PENALTY_LD
            ):
                return 'L'
            case Result.UNRATED_DRAW | Result.UNRATED_PENALTY_DL:
                return 'D'
            case Result.UNRATED_WIN:
                return 'W'
            case Result.FORFEIT_LOSS | Result.DOUBLE_FORFEIT:
                return '-'
            case Result.FORFEIT_WIN:
                return '+'
            case Result.HALF_POINT_BYE:
                return 'H'
            case Result.FULL_POINT_BYE:
                return 'F'
            case Result.PAIRING_ALLOCATED_BYE:
                return 'U'
            case Result.ZERO_POINT_BYE:
                return 'Z'
            case Result.NO_RESULT | Result.REST_GAME:
                return ' '
            case _:
                raise ValueError(f'Unknown value: {self}')

    @classmethod
    def from_trf(cls, value: str, opponent_value: str):
        match value.upper():
            case '' | 'Z':
                return cls.ZERO_POINT_BYE
            case '1':
                return cls.WIN
            case '=':
                return cls.PENALTY_DL if opponent_value == '0' else cls.DRAW
            case '0':
                match opponent_value:
                    case '0':
                        return cls.PENALTY_LL
                    case '=':
                        return cls.PENALTY_LD
                    case _:
                        return cls.LOSS
            case 'W':
                return cls.UNRATED_WIN
            case 'D':
                return (
                    cls.UNRATED_PENALTY_DL
                    if opponent_value == 'L'
                    else cls.UNRATED_DRAW
                )
            case 'L':
                match opponent_value:
                    case 'L':
                        return cls.UNRATED_PENALTY_LL
                    case 'D':
                        return cls.UNRATED_PENALTY_LD
                    case _:
                        return cls.UNRATED_LOSS
            case '+':
                return cls.FORFEIT_WIN
            case '-':
                return cls.FORFEIT_LOSS
            case 'U':
                return cls.PAIRING_ALLOCATED_BYE
            case 'F':
                return cls.FULL_POINT_BYE
            case 'H':
                return cls.HALF_POINT_BYE
            case _:
                raise ValueError(f'Unknown value: {value}')

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
    def is_bye(self) -> bool:
        return self in (
            Result.ZERO_POINT_BYE,
            Result.HALF_POINT_BYE,
            Result.FULL_POINT_BYE,
            Result.PAIRING_ALLOCATED_BYE,
            Result.REST_GAME,
        )

    @property
    def unplayed(self) -> bool:
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
                return _('Elo *** STD ELO FOR TABLE HEADER')
            case TournamentRating.RAPID:
                return _('Rapid *** RAPID ELO FOR TABLE HEADER')
            case TournamentRating.BLITZ:
                return _('Blitz *** BLITZ ELO FOR TABLE HEADER')
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

    def __str__(self) -> str:
        return self.name


class PlayerGender(IntEnum):
    NONE = 0
    FEMALE = 1
    MALE = 2

    @classmethod
    def values(cls) -> tuple[int, ...]:
        return tuple(item.value for item in cls)

    @classmethod
    def from_fide_value(cls, value: str) -> 'PlayerGender':
        match value:
            case 'F' | 'f':
                return cls.FEMALE
            case 'M' | 'm':
                return cls.MALE
            case _:
                raise ValueError(f'Unknown value: {value}')

    @property
    def to_trf(self) -> str:
        match self:
            case PlayerGender.NONE:
                return ''
            case PlayerGender.FEMALE:
                return 'w'
            case PlayerGender.MALE:
                return 'm'
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def name(self) -> str:
        match self:
            case PlayerGender.NONE:
                return _('- *** NAME FOR GENDER NONE')
            case PlayerGender.FEMALE:
                return _('Female *** NAME FOR GENDER FEMALE')
            case PlayerGender.MALE:
                return _('Male *** NAME FOR GENDER MALE')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def short_name(self) -> str:
        match self:
            case PlayerGender.NONE:
                return _('- *** SHORT NAME FOR GENDER NONE')
            case PlayerGender.FEMALE:
                return _('F *** SHORT NAME FOR GENDER FEMALE')
            case PlayerGender.MALE:
                return _('M *** SHORT NAME FOR GENDER MALE')
            case _:
                raise ValueError(f'Unknown value: {self}')


class PlayerCategory(IntEnum):
    NONE = 0
    U8 = 1
    U10 = 2
    U12 = 3
    U14 = 4
    U16 = 5
    U18 = 6
    U20 = 7
    O20 = 8
    O50 = 9
    O65 = 10

    @property
    def short_name(self) -> str:
        match self:
            case PlayerCategory.NONE:
                return ''
            case PlayerCategory.U8:
                return _('U8')
            case PlayerCategory.U10:
                return _('U10')
            case PlayerCategory.U12:
                return _('U12')
            case PlayerCategory.U14:
                return _('U14')
            case PlayerCategory.U16:
                return _('U16')
            case PlayerCategory.U18:
                return _('U18')
            case PlayerCategory.U20:
                return _('U20')
            case PlayerCategory.O20:
                return _('20+')
            case PlayerCategory.O50:
                return _('50+')
            case PlayerCategory.O65:
                return _('65+')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def name(self) -> str:
        match self:
            case PlayerCategory.NONE:
                return _('No category')
            case PlayerCategory.U8:
                return _('Under 8')
            case PlayerCategory.U10:
                return _('Under 10')
            case PlayerCategory.U12:
                return _('Under 12')
            case PlayerCategory.U14:
                return _('Under 14')
            case PlayerCategory.U16:
                return _('Under 16')
            case PlayerCategory.U18:
                return _('Under 18')
            case PlayerCategory.U20:
                return _('Under 20')
            case PlayerCategory.O20:
                return _('Over 20')
            case PlayerCategory.O50:
                return _('Over 50')
            case PlayerCategory.O65:
                return _('Over 65')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @staticmethod
    def from_year_of_birth(
        year_of_birth: int | None,
        tournament_start: datetime | None = None,
        tournament_end: datetime | None = None,
    ) -> 'PlayerCategory':
        from plugins.manager import plugin_manager

        if not year_of_birth:
            return PlayerCategory.NONE

        if tournament_start and tournament_end:
            start_d = tournament_start.date()
            end_d = tournament_end.date()
            if (end_d - start_d) > timedelta(days=30):
                base = date.today()
                if base < start_d:
                    ref_date = start_d
                elif base > end_d:
                    ref_date = end_d
                else:
                    ref_date = base
            else:
                ref_date = start_d
        else:
            ref_date = date.today()

        ref_year: int = (
            plugin_manager.hook.adjust_category_reference_year(reference_date=ref_date)
            or ref_date.year
        )

        age = ref_year - year_of_birth
        if age <= 8:
            return PlayerCategory.U8
        elif age <= 10:
            return PlayerCategory.U10
        elif age <= 12:
            return PlayerCategory.U12
        elif age <= 14:
            return PlayerCategory.U14
        elif age <= 16:
            return PlayerCategory.U16
        elif age <= 18:
            return PlayerCategory.U18
        elif age <= 20:
            return PlayerCategory.U20
        elif age <= 50:
            return PlayerCategory.O20
        elif age <= 65:
            return PlayerCategory.O50
        else:
            return PlayerCategory.O65

    def __str__(self) -> str:
        return self.short_name


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

    def __str__(self) -> str:
        return self.short_name


class PlayerTitle(IntEnum):
    """The possible FIDE titles: GM, WGM, IM, WIM, FM, WFM, CM, WCM.
    Also includes the "no title" case.
    This is for Papi-compatibility reasons."""

    NONE = 0
    WOMAN_CANDIDATE_MASTER = 1
    CANDIDATE_MASTER = 2
    WOMAN_FIDE_MASTER = 3
    FIDE_MASTER = 4
    WOMAN_INTERNATIONAL_MASTER = 5
    INTERNATIONAL_MASTER = 6
    WOMAN_GRANDMASTER = 7
    GRANDMASTER = 8

    @classmethod
    def from_fide_value(cls, value: str) -> 'PlayerTitle':
        match value.strip():
            case '':
                return PlayerTitle.NONE
            case 'WCM':
                return PlayerTitle.WOMAN_CANDIDATE_MASTER
            case 'CM':
                return PlayerTitle.CANDIDATE_MASTER
            case 'WFM':
                return PlayerTitle.WOMAN_FIDE_MASTER
            case 'FM':
                return PlayerTitle.FIDE_MASTER
            case 'WIM':
                return PlayerTitle.WOMAN_INTERNATIONAL_MASTER
            case 'IM':
                return PlayerTitle.INTERNATIONAL_MASTER
            case 'WGM':
                return PlayerTitle.WOMAN_GRANDMASTER
            case 'GM':
                return PlayerTitle.GRANDMASTER
            case _:
                raise ValueError(f'Unknown title value: {value}')

    @property
    def to_fide_value(self) -> str:
        match self:
            case PlayerTitle.NONE:
                return ''
            case PlayerTitle.WOMAN_CANDIDATE_MASTER:
                return 'WCM'
            case PlayerTitle.CANDIDATE_MASTER:
                return 'CM'
            case PlayerTitle.WOMAN_FIDE_MASTER:
                return 'WFM'
            case PlayerTitle.FIDE_MASTER:
                return 'FM'
            case PlayerTitle.WOMAN_INTERNATIONAL_MASTER:
                return 'WIM'
            case PlayerTitle.INTERNATIONAL_MASTER:
                return 'IM'
            case PlayerTitle.WOMAN_GRANDMASTER:
                return 'WGM'
            case PlayerTitle.GRANDMASTER:
                return 'GM'
            case _:
                raise ValueError(f'Unknown title: {self}')

    @property
    def to_trf(self) -> str:
        match self:
            case PlayerTitle.NONE:
                return ''
            case PlayerTitle.WOMAN_CANDIDATE_MASTER:
                return 'cf'
            case PlayerTitle.CANDIDATE_MASTER:
                return 'c'
            case PlayerTitle.WOMAN_FIDE_MASTER:
                return 'ff'
            case PlayerTitle.FIDE_MASTER:
                return 'f'
            case PlayerTitle.WOMAN_INTERNATIONAL_MASTER:
                return 'mf'
            case PlayerTitle.INTERNATIONAL_MASTER:
                return 'm'
            case PlayerTitle.WOMAN_GRANDMASTER:
                return 'gf'
            case PlayerTitle.GRANDMASTER:
                return 'g'
            case _:
                raise ValueError(f'Unknown title: {self}')

    @property
    def name(self) -> str:
        match self:
            case PlayerTitle.NONE:
                return _('No title')
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


class BoardColor(StrEnum):
    WHITE = 'W'
    BLACK = 'B'

    @property
    def to_trf(self) -> str:
        match self:
            case BoardColor.WHITE:
                return 'w'
            case BoardColor.BLACK:
                return 'b'
            case _:
                raise ValueError(f'Unknown value:  {self}')

    @property
    def to_trf_first_round_pairing(self) -> str:
        match self:
            case BoardColor.WHITE:
                return 'white1'
            case BoardColor.BLACK:
                return 'black1'
            case _:
                raise ValueError(f'Unknown value:  {self}')

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
    BOARDS = 'boards'
    INPUT = 'input'
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
            case ScreenType.INPUT:
                return _('Results entry')
            case ScreenType.PLAYERS:
                return _('Parings by player')
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
    def families_allowed(self) -> bool:
        """Returns True if the screen type can be used for families, False otherwise."""
        match self:
            case self.BOARDS | self.INPUT | self.PLAYERS | self.RANKING:
                return True
            case self.RESULTS | self.IMAGE:
                return False
            case _:
                raise ValueError(f'Invalid screen type: {self}')


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


class TrfType(StrEnum):
    TRF_16 = 'trf-16'
    TRF_BX = 'trf-bx'


class FormAction(StrEnum):
    UPDATE = 'update'
    CREATE = 'create'
    CLONE = 'clone'
    DELETE = 'delete'
