"""A file grouping all the "utility" classes/enum: Result, Color, PlayerTitle,
PlayerSex, TournamentPairing, TournamentRating"""

from datetime import datetime
from enum import Enum, StrEnum, IntEnum, auto
from itertools import islice
from logging import Logger
from typing import Self

from common.i18n import _
from common.logger import get_logger

logger: Logger = get_logger()


try:
    import itertools

    batched = itertools.batched
except AttributeError:

    def batched(iterable, n):
        """Batch data from the *iterable* into tuples of length *n*.
        The last batch may be shorter than *n*"""
        if n < 1:
            raise ValueError("n must be at least 1")
        iterator = iter(iterable)
        while batch := tuple(islice(iterator, n)):
            yield batch


class PapiResult(IntEnum):
    """An enum representing the results in the Papi database"""

    NOT_PAIRED = 0
    LOSS = 1
    DRAW_OR_HPB = 2  # HPB = Half Point Bye
    GAIN = 3
    FORFEIT_LOSS = 4
    DOUBLE_FORFEIT = 5
    PAB_OR_FORFEIT_GAIN_OR_FPB = 6  # PAB = Pairing-Allocated-Bye, FPB = Full Point Bye


class Result(IntEnum):
    """An enum representing the results in the database. Should be subclassed if the point value is not the default."""

    NO_RESULT = 0  # NOT PAIRED or NO RESULT YET
    LOSS = 1
    DRAW = 2
    GAIN = 3
    FORFEIT_LOSS = 4
    DOUBLE_FORFEIT = 5
    FORFEIT_GAIN = 6
    ZERO_POINT_BYE = 7
    HALF_POINT_BYE = 8
    PAIRING_ALLOCATED_BYE = 9
    FULL_POINT_BYE = 10
    UNRATED_LOSS = 11
    UNRATED_DRAW = 12
    UNRATED_GAIN = 13

    def __str__(self) -> str:
        match self:
            case Result.GAIN | Result.UNRATED_GAIN:
                return "1-0"
            case Result.LOSS | Result.UNRATED_LOSS:
                return "0-1"
            case Result.DRAW | Result.UNRATED_DRAW | Result.HALF_POINT_BYE:
                return "1/2"
            case Result.NO_RESULT | Result.ZERO_POINT_BYE:
                return ""
            case Result.FORFEIT_LOSS:
                return "F-1"
            case (
                Result.FORFEIT_GAIN
                | Result.PAIRING_ALLOCATED_BYE
                | Result.FULL_POINT_BYE
            ):
                return "1-F"
            case Result.DOUBLE_FORFEIT:
                return "F-F"
            case _:
                raise ValueError(f"Unknown value: {self}")

    @classmethod
    def from_papi_value(
        cls,
        value: int,
        is_point_bye: bool = False,
        is_pairing_bye: bool = False,
        is_zero_point_bye: bool = False,
        is_unrated: bool = False,
    ) -> Self:
        """Create a `Result` instance from the stored value in the
        Papi database."""
        match value:
            case PapiResult.NOT_PAIRED.value if is_zero_point_bye:
                return cls.ZERO_POINT_BYE
            case PapiResult.NOT_PAIRED.value:
                return cls.NO_RESULT
            case PapiResult.LOSS.value if is_unrated:
                return cls.UNRATED_LOSS
            case PapiResult.LOSS.value:
                return cls.LOSS
            case PapiResult.DRAW_OR_HPB.value if is_unrated:
                return cls.UNRATED_DRAW
            case PapiResult.DRAW_OR_HPB.value if is_point_bye:
                return cls.HALF_POINT_BYE
            case PapiResult.DRAW_OR_HPB.value:
                return cls.DRAW
            case PapiResult.GAIN.value if is_unrated:
                return cls.UNRATED_GAIN
            case PapiResult.GAIN.value:
                return cls.GAIN
            case PapiResult.GAIN.value:
                return cls.UNRATED_GAIN if is_unrated else cls.GAIN
            case PapiResult.PAB_OR_FORFEIT_GAIN_OR_FPB.value if is_point_bye:
                return cls.FULL_POINT_BYE
            case PapiResult.PAB_OR_FORFEIT_GAIN_OR_FPB.value if is_pairing_bye:
                return cls.PAIRING_ALLOCATED_BYE
            case PapiResult.PAB_OR_FORFEIT_GAIN_OR_FPB.value:
                return cls.FORFEIT_GAIN
            case PapiResult.FORFEIT_LOSS.value:
                return cls.FORFEIT_LOSS
            case PapiResult.DOUBLE_FORFEIT.value:
                return cls.DOUBLE_FORFEIT
            case _:
                raise ValueError(f"Unknown value: {value}")

    @property
    def to_papi_result(self) -> PapiResult:
        match self:
            case Result.GAIN | Result.UNRATED_GAIN:
                return PapiResult.GAIN
            case Result.LOSS | Result.UNRATED_LOSS:
                return PapiResult.LOSS
            case Result.DRAW | Result.UNRATED_DRAW | Result.HALF_POINT_BYE:
                return PapiResult.DRAW_OR_HPB
            case Result.NO_RESULT | Result.ZERO_POINT_BYE:
                return PapiResult.NOT_PAIRED
            case Result.FORFEIT_LOSS:
                return PapiResult.FORFEIT_LOSS
            case (
                Result.FORFEIT_GAIN
                | Result.PAIRING_ALLOCATED_BYE
                | Result.FULL_POINT_BYE
            ):
                return PapiResult.PAB_OR_FORFEIT_GAIN_OR_FPB
            case Result.DOUBLE_FORFEIT:
                return PapiResult.DOUBLE_FORFEIT
            case _:
                raise ValueError(f"Unknown value: {self}")

    @property
    def to_papi_value(self) -> int:
        return self.to_papi_result.value

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
            ):
                return 0.0
            case Result.DRAW | Result.UNRATED_DRAW | Result.HALF_POINT_BYE:
                return 0.5
            case (
                Result.GAIN
                | Result.UNRATED_GAIN
                | Result.FORFEIT_GAIN
                | Result.PAIRING_ALLOCATED_BYE
                | Result.FULL_POINT_BYE
            ):
                return 1.0

    @property
    def opposite_result(self) -> Self:
        """Given a `Result` instance (white result), returns the result of the
        opponent.

        >>> Result.GAIN.opposite_result == Result.LOSS
        True

        >>> Result.LOSS.opposite_result == Result.GAIN
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
                return Result.GAIN
            case Result.GAIN:
                return Result.LOSS
            case Result.DRAW:
                return Result.DRAW
            case Result.UNRATED_LOSS:
                return Result.UNRATED_GAIN
            case Result.UNRATED_GAIN:
                return Result.UNRATED_LOSS
            case Result.UNRATED_DRAW:
                return Result.UNRATED_DRAW
            case Result.FORFEIT_GAIN:
                return Result.FORFEIT_LOSS
            case Result.FORFEIT_LOSS:
                return Result.FORFEIT_GAIN
            case Result.DOUBLE_FORFEIT:
                return Result.DOUBLE_FORFEIT
            case Result.NO_RESULT:
                return Result.NO_RESULT
            case (
                Result.ZERO_POINT_BYE
                | Result.HALF_POINT_BYE
                | Result.PAIRING_ALLOCATED_BYE
                | Result.FULL_POINT_BYE
            ):
                raise ValueError(f"Result '{self}' is not reversible")
            case _:
                raise ValueError(f"Unknown value: {self}")

    @property
    def to_trf(self) -> str:
        match self:
            case Result.LOSS:
                return "0"
            case Result.DRAW:
                return "="
            case Result.GAIN:
                return "1"
            case Result.UNRATED_LOSS:
                return "L"
            case Result.UNRATED_DRAW:
                return "D"
            case Result.UNRATED_GAIN:
                return "W"
            case Result.FORFEIT_LOSS | Result.DOUBLE_FORFEIT:
                return "-"
            case Result.FORFEIT_GAIN:
                return "+"
            case Result.HALF_POINT_BYE:
                return "H"
            case Result.FULL_POINT_BYE:
                return "F"
            case Result.PAIRING_ALLOCATED_BYE:
                return "U"
            case Result.ZERO_POINT_BYE:
                return "Z"
            case Result.NO_RESULT:
                return " "
            case _:
                raise ValueError(f"Unknown value: {self}")

    @property
    def bbp_field(self) -> str:
        match self:
            case Result.LOSS:
                return "BBL"
            case Result.DRAW:
                return "BBD"
            case Result.GAIN:
                return "BBW"
            case Result.FORFEIT_LOSS:
                return "BBF"
            case Result.PAIRING_ALLOCATED_BYE:
                return "BBU"
            case Result.ZERO_POINT_BYE:
                return "BBZ"
            case _:
                raise ValueError(f"Result with no matching BBP field: {self}")

    @property
    def is_bye(self) -> bool:
        return self in (
            Result.ZERO_POINT_BYE,
            Result.HALF_POINT_BYE,
            Result.FULL_POINT_BYE,
            Result.PAIRING_ALLOCATED_BYE,
        )

    @classmethod
    def user_imputable_results(cls) -> tuple[Self, ...]:
        """Imputable results are the ones that a player can
        input by themselves, namely a win, a draw, or a loss or forfeits."""
        return cls.GAIN, cls.DRAW, cls.LOSS

    @classmethod
    def admin_imputable_results(cls) -> tuple[Self, ...]:
        """Admin imputable results are the ones that only arbiters can input."""
        return cls.user_imputable_results() + (
            cls.FORFEIT_GAIN,
            cls.FORFEIT_LOSS,
            cls.DOUBLE_FORFEIT,
        )


class TournamentType(IntEnum):
    """An enumeration representing the supported types of tournaments."""

    UNKNOWN = 0
    SWISS = 1
    CHAMPIONSHIP = 2

    @classmethod
    def from_papi_value(cls, value) -> Self:
        match value:
            case "Suisse":
                return cls.SWISS
            case "ToutesRondes":
                return cls.CHAMPIONSHIP
            case _:
                raise ValueError(f"Unknown value: {value}")

    @property
    def to_papi_value(self) -> str:
        match self:
            case TournamentType.SWISS:
                return "Suisse"
            case TournamentType.CHAMPIONSHIP:
                return "ToutesRondes"
            case _:
                raise ValueError(f"Unknown tie break: {self}")

    def __str__(self) -> str:
        # TODO Translate this (if used)!
        match self:
            case TournamentType.UNKNOWN:
                return "Inconnu"
            case TournamentType.SWISS:
                return "Système suisse"
            case TournamentType.CHAMPIONSHIP:
                return "Toutes rondes"
            case _:
                raise ValueError(f"Unknown tie break: {self}")


class TournamentRating(IntEnum):
    """A wrapper around the tournament rating used stored in the papi db."""

    STANDARD = 1
    RAPID = 2
    BLITZ = 3

    @classmethod
    def from_papi_value(cls, value) -> Self:
        match value:
            case "Elo":
                return cls.STANDARD
            case "Rapide":
                return cls.RAPID
            case "Blitz":
                return cls.BLITZ
            case _:
                raise ValueError(f"Unknown value: {value}")

    @property
    def to_papi_value(self) -> str:
        match self:
            case TournamentRating.STANDARD:
                return "Elo"
            case TournamentRating.RAPID:
                return "Rapide"
            case TournamentRating.BLITZ:
                return "Blitz"
            case _:
                raise ValueError(f"Unknown value: {self}")

    @property
    def papi_value_field(self) -> str:
        match self:
            case TournamentRating.STANDARD:
                return "Elo"
            case TournamentRating.RAPID:
                return "Rapide"
            case TournamentRating.BLITZ:
                return "Blitz"
            case _:
                raise ValueError(f"Unknown value: {self}")

    @property
    def papi_type_field(self) -> str:
        match self:
            case TournamentRating.STANDARD:
                return "Fide"
            case TournamentRating.RAPID:
                return "RapideFide"
            case TournamentRating.BLITZ:
                return "BlitzFide"
            case _:
                raise ValueError(f"Unknown value: {self}")

    def __str__(self) -> str:
        match self:
            case TournamentRating.STANDARD:
                return _("Standard rating")
            case TournamentRating.RAPID:
                return _("Rapid rating")
            case TournamentRating.BLITZ:
                return _("Blitz rating")
            case _:
                raise ValueError(f"Unknown rating: {self}")


class TournamentPairing(IntEnum):
    """An enumeration representing the supported types of tournament
    pairings.
    Swiss Dutch with acceleration and Berger-table tournaments are supported."""

    UNKNOWN = 0
    STANDARD = 1
    HALEY = 2
    HALEY_SOFT = 3
    SAD = 4
    NICOIS = 5
    BERGER = 6

    @classmethod
    def from_papi_value(cls, value) -> Self:
        match value:
            case "Standard":
                return cls.STANDARD
            case "Haley":
                return cls.HALEY
            case "HaleySoft":
                return cls.HALEY_SOFT
            case "SAD":
                return cls.SAD
            case "Nicois":
                return cls.NICOIS
            case "Berger":
                return cls.BERGER
            case _:
                raise ValueError(f"Unknown value: {value}")

    @property
    def to_papi_value(self) -> str:
        match self:
            case TournamentPairing.STANDARD:
                return "Standard"
            case TournamentPairing.HALEY:
                return "Haley"
            case TournamentPairing.HALEY_SOFT:
                return "HaleySoft"
            case TournamentPairing.SAD:
                return "SAD"
            case TournamentPairing.NICOIS:
                return "Nicois"
            case TournamentPairing.BERGER:
                return "Berger"
            case _:
                raise ValueError(f"Unknown value: {self}")

    def __str__(self) -> str:
        # TODO Translate this (if used)!
        match self:
            case TournamentPairing.UNKNOWN:
                return "Inconnu"
            case TournamentPairing.STANDARD:
                return "Système suisse standard"
            case TournamentPairing.HALEY:
                return "Système de Haley"
            case TournamentPairing.HALEY_SOFT:
                return "Système de Haley dégressif"
            case TournamentPairing.SAD:
                return "Système accéléré dégressif (SAD)"
            case TournamentPairing.NICOIS:
                return "Système accéléré niçois"
            case TournamentPairing.BERGER:
                return "Berger"
            case _:
                raise ValueError(f"Unknown pairing type: {self}")


class TournamentTieBreak(IntEnum):
    """An enumeration representing the supported types of tournament
    tie breaks."""

    NONE = 0
    BUCHHOLZ = 1
    BUCHHOLZ_CUT_TOP = 2
    BUCHHOLZ_CUT_TOP_BOTTOM = 3
    CUMULATIVE = 4
    PERFORMANCE = 5
    BUCHHOLZ_SUM = 6
    WINS = 7
    KASHDAN = 8
    KOYA = 9
    SONNENBORN_BERGER = 10

    @classmethod
    def from_papi_value(cls, value) -> Self:
        match value:
            case "":
                return cls.NONE
            case "Solkoff":
                return cls.BUCHHOLZ
            case "Brésilien":
                return cls.BUCHHOLZ_CUT_TOP
            case "Harkness":
                return cls.BUCHHOLZ_CUT_TOP_BOTTOM
            case "Cumulatif":
                return cls.CUMULATIVE
            case "Performance":
                return cls.PERFORMANCE
            case "SommeDesBuchholz":
                return cls.BUCHHOLZ_SUM
            case "Nombre de Victoires":
                return cls.WINS
            case "Kashdan":
                return cls.KASHDAN
            case "Koya":
                return cls.KOYA
            case "Sonnenborn-Berger":
                return cls.SONNENBORN_BERGER
            case _:
                raise ValueError(f"Unknown value: {value}")

    @property
    def to_papi_value(self) -> str:
        match self:
            case TournamentTieBreak.NONE:
                return ""
            case TournamentTieBreak.BUCHHOLZ:
                return "Solkoff"
            case TournamentTieBreak.BUCHHOLZ_CUT_TOP:
                return "Brésilien"
            case TournamentTieBreak.BUCHHOLZ_CUT_TOP_BOTTOM:
                return "Harkness"
            case TournamentTieBreak.CUMULATIVE:
                return "Cumulatif"
            case TournamentTieBreak.PERFORMANCE:
                return "Performance"
            case TournamentTieBreak.BUCHHOLZ_SUM:
                return "SommeDesBuchholz"
            case TournamentTieBreak.WINS:
                return "Nombre de Victoires"
            case TournamentTieBreak.KASHDAN:
                return "Kashdan"
            case TournamentTieBreak.KOYA:
                return "Koya"
            case TournamentTieBreak.SONNENBORN_BERGER:
                return "Sonnenborn-Berger"
            case _:
                raise ValueError(f"Unknown tie break: {self}")

    def __str__(self) -> str:
        # TODO Translate this (if used)!
        match self:
            case TournamentTieBreak.NONE:
                return "Aucun"
            case TournamentTieBreak.BUCHHOLZ:
                return "Buchholz"
            case TournamentTieBreak.BUCHHOLZ_CUT_TOP:
                return "Buchholz tronqué"
            case TournamentTieBreak.BUCHHOLZ_CUT_TOP_BOTTOM:
                return "Buchholz médian"
            case TournamentTieBreak.CUMULATIVE:
                return "Cumulatif"
            case TournamentTieBreak.PERFORMANCE:
                return "Performance"
            case TournamentTieBreak.BUCHHOLZ_SUM:
                return "Somme des buchholz"
            case TournamentTieBreak.WINS:
                return "Nombre de victoire"
            case TournamentTieBreak.KASHDAN:
                return "Kashdan"
            case TournamentTieBreak.KOYA:
                return "Koya"
            case TournamentTieBreak.SONNENBORN_BERGER:
                return "Sonnenborn-Berger"
            case _:
                raise ValueError(f"Unknown tie break: {self}")


class PlayerGender(IntEnum):
    NONE = 0
    FEMALE = 1
    MALE = 2

    @classmethod
    def values(cls) -> tuple[int, ...]:
        return tuple(item.value for item in cls)

    @classmethod
    def from_papi_value(cls, value: str) -> Self:
        match value:
            case "":
                return cls.NONE
            case "F" | "f":
                return cls.FEMALE
            case "M" | "m":
                return cls.MALE
            case _:
                raise ValueError(f"Unknown value: {value}")

    @property
    def to_papi_value(self) -> str:
        match self:
            case PlayerGender.NONE:
                return ""
            case PlayerGender.FEMALE:
                return "F"
            case PlayerGender.MALE:
                return "M"
            case _:
                raise ValueError(f"Unknown value: {self}")

    @classmethod
    def from_fide_value(cls, value: str) -> Self:
        match value:
            case "F" | "f":
                return cls.FEMALE
            case "M" | "m":
                return cls.MALE
            case _:
                raise ValueError(f"Unknown value: {value}")

    @property
    def to_trf(self) -> str:
        match self:
            case PlayerGender.NONE:
                return ""
            case PlayerGender.FEMALE:
                return "w"
            case PlayerGender.MALE:
                return "m"
            case _:
                raise ValueError(f"Unknown value: {self}")

    @property
    def name(self) -> str:
        match self:
            case PlayerGender.NONE:
                return _("- *** NAME FOR GENDER NONE")
            case PlayerGender.FEMALE:
                return _("Female *** NAME FOR GENDER FEMALE")
            case PlayerGender.MALE:
                return _("Male *** NAME FOR GENDER MALE")
            case _:
                raise ValueError(f"Unknown value: {self}")

    @property
    def short_name(self) -> str:
        match self:
            case PlayerGender.NONE:
                return _("- *** SHORT NAME FOR GENDER NONE")
            case PlayerGender.FEMALE:
                return _("F *** SHORT NAME FOR GENDER FEMALE")
            case PlayerGender.MALE:
                return _("M *** SHORT NAME FOR GENDER MALE")
            case _:
                raise ValueError(f"Unknown value: {self}")


class PlayerFFELicence(IntEnum):
    NONE = 0
    N = 1
    A = 2
    B = 3

    @classmethod
    def from_papi_value(cls, value: str) -> Self:
        match value:
            case "":
                return cls.NONE
            case "N":
                return cls.N
            case "A":
                return cls.A
            case "B":
                return cls.B
            case _:
                raise ValueError(f"Unknown value: {value}")

    @property
    def to_papi_value(self) -> str:
        match self:
            case PlayerFFELicence.NONE:
                return ""
            case PlayerFFELicence.N:
                return "N"
            case PlayerFFELicence.A:
                return "A"
            case PlayerFFELicence.B:
                return "B"
            case _:
                raise ValueError(f"Unknown value: {self}")

    @classmethod
    def from_chessevent_value(cls, value: int) -> Self:
        match value:
            case 0:
                return cls.NONE
            case 1:
                return cls.N
            case 2:
                return cls.B
            case 3:
                return cls.A
            case _:
                raise ValueError(f"Unknown value: {value}")

    @property
    def name(self) -> str:
        match self:
            case PlayerFFELicence.NONE:
                return _("No FFE Licence")
            case PlayerFFELicence.N:
                return _("Expired FFE licence")
            case PlayerFFELicence.B:
                return _("FFE licence B (leisure)")
            case PlayerFFELicence.A:
                return _("FFE licence A (competition)")
            case _:
                raise ValueError(f"Unknown value: {self}")

    @property
    def short_name(self) -> str:
        match self:
            case PlayerFFELicence.NONE:
                return "-"
            case PlayerFFELicence.N:
                return "N"
            case PlayerFFELicence.A:
                return "A"
            case PlayerFFELicence.B:
                return "B"
            case _:
                raise ValueError(f"Unknown value: {self}")


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

    @classmethod
    def from_papi_value(cls, value: str) -> Self:
        match value:
            case "":
                return cls.NONE
            case "Ppo":
                return cls.U8
            case "Pou":
                return cls.U10
            case "Pup":
                return cls.U12
            case "Ben":
                return cls.U14
            case "Min":
                return cls.U16
            case "Cad":
                return cls.U18
            case "Jun":
                return cls.U20
            case "Sen":
                return cls.O20
            case "Sep":
                return cls.O50
            case "Vet":
                return cls.O65
            case _:
                raise ValueError(f"Unknown value: {value}")

    @property
    def to_papi_value(self) -> str:
        match self:
            case PlayerCategory.NONE:
                return ""
            case PlayerCategory.U8:
                return "Ppo"
            case PlayerCategory.U10:
                return "Pou"
            case PlayerCategory.U12:
                return "Pup"
            case PlayerCategory.U14:
                return "Ben"
            case PlayerCategory.U16:
                return "Min"
            case PlayerCategory.U18:
                return "Cad"
            case PlayerCategory.U20:
                return "Jun"
            case PlayerCategory.O20:
                return "Sen"
            case PlayerCategory.O50:
                return "Sep"
            case PlayerCategory.O65:
                return "Vet"
            case _:
                raise ValueError(f"Unknown value: {self}")

    @property
    def short_name(self) -> str:
        match self:
            case PlayerCategory.NONE:
                return ""
            case PlayerCategory.U8:
                return _("U8")
            case PlayerCategory.U10:
                return _("U10")
            case PlayerCategory.U12:
                return _("U12")
            case PlayerCategory.U14:
                return _("U14")
            case PlayerCategory.U16:
                return _("U16")
            case PlayerCategory.U18:
                return _("U18")
            case PlayerCategory.U20:
                return _("U20")
            case PlayerCategory.O20:
                return _("20+")
            case PlayerCategory.O50:
                return _("50+")
            case PlayerCategory.O65:
                return _("65+")
            case _:
                raise ValueError(f"Unknown value: {self}")

    @property
    def name(self) -> str:
        match self:
            case PlayerCategory.NONE:
                return _("No category")
            case PlayerCategory.U8:
                return _("Under 8")
            case PlayerCategory.U10:
                return _("Under 10")
            case PlayerCategory.U12:
                return _("Under 12")
            case PlayerCategory.U14:
                return _("Under 14")
            case PlayerCategory.U16:
                return _("Under 16")
            case PlayerCategory.U18:
                return _("Under 18")
            case PlayerCategory.U20:
                return _("Under 20")
            case PlayerCategory.O20:
                return _("Over 20")
            case PlayerCategory.O50:
                return _("Over 50")
            case PlayerCategory.O65:
                return _("Over 65")
            case _:
                raise ValueError(f"Unknown value: {self}")

    @staticmethod
    def from_year_of_birth(year_of_birth: int | None) -> "PlayerCategory":
        if not year_of_birth:
            return PlayerCategory.NONE
        now: datetime = datetime.now()
        ref_year: int = now.year if now.month < 9 else now.year + 1
        age: int = ref_year - year_of_birth
        if age < 8:
            return PlayerCategory.U8
        elif age < 10:
            return PlayerCategory.U10
        elif age < 12:
            return PlayerCategory.U12
        elif age < 14:
            return PlayerCategory.U14
        elif age < 16:
            return PlayerCategory.U16
        elif age < 18:
            return PlayerCategory.U18
        elif age < 20:
            return PlayerCategory.U20
        elif age < 50:
            return PlayerCategory.O20
        elif age < 65:
            return PlayerCategory.O50
        else:
            return PlayerCategory.O65

    def __str__(self) -> str:
        return self.short_name


class PlayerRatingType(IntEnum):
    ESTIMATED = 1
    NATIONAL = 2
    FIDE = 3

    @classmethod
    def from_papi_value(cls, value: str) -> Self:
        match value:
            case "E":
                return cls.ESTIMATED
            case "N":
                return cls.NATIONAL
            case "F":
                return cls.FIDE
            case _:
                raise ValueError(f"Unknown value: {value}")

    @property
    def to_papi_value(self) -> str:
        match self:
            case PlayerRatingType.ESTIMATED:
                return "E"
            case PlayerRatingType.NATIONAL:
                return "N"
            case PlayerRatingType.FIDE:
                return "F"
            case _:
                raise ValueError(f"Unknown value: {self}")

    @property
    def name(self) -> str:
        match self:
            case PlayerRatingType.ESTIMATED:
                return _("Estimated *** NAME FOR RATING TYPE ESTIMATED")
            case PlayerRatingType.NATIONAL:
                return _("National *** NAME FOR RATING TYPE NATIONAL")
            case PlayerRatingType.FIDE:
                return _("FIDE *** NAME FOR RATING TYPE FIDE")
            case _:
                raise ValueError(f"Unknown value: {self}")

    @property
    def short_name(self) -> str:
        match self:
            case PlayerRatingType.ESTIMATED:
                return _("E *** SHORT NAME FOR RATING TYPE ESTIMATED")
            case PlayerRatingType.NATIONAL:
                return _("N *** SHORT NAME FOR RATING TYPE NATIONAL")
            case PlayerRatingType.FIDE:
                return _("F *** SHORT NAME FOR RATING TYPE FIDE")
            case _:
                raise ValueError(f"Unknown value: {self}")

    def __str__(self) -> str:
        return self.short_name


class PlayerTitle(IntEnum):
    """The possible FIDE titles: GM, WGM, IM, WIM, FM, WFM.
    Also includes the "no title" case, but does not include CM nor WCM.
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
    def from_papi_value(cls, value: str) -> Self:
        match value.strip():
            case "":
                return PlayerTitle.NONE
            case "ff":
                return PlayerTitle.WOMAN_FIDE_MASTER
            case "f":
                return PlayerTitle.FIDE_MASTER
            case "mf":
                return PlayerTitle.WOMAN_INTERNATIONAL_MASTER
            case "m":
                return PlayerTitle.INTERNATIONAL_MASTER
            case "gf":
                return PlayerTitle.WOMAN_GRANDMASTER
            case "g":
                return PlayerTitle.GRANDMASTER
            case _:
                raise ValueError(f"Unknown title value: {value}")

    @property
    def to_papi_value(self) -> str:
        match self:
            case (
                PlayerTitle.NONE
                | PlayerTitle.WOMAN_CANDIDATE_MASTER
                | PlayerTitle.CANDIDATE_MASTER
            ):
                return ""
            case PlayerTitle.WOMAN_FIDE_MASTER:
                return "ff"
            case PlayerTitle.FIDE_MASTER:
                return "f"
            case PlayerTitle.WOMAN_INTERNATIONAL_MASTER:
                return "mf"
            case PlayerTitle.INTERNATIONAL_MASTER:
                return "m"
            case PlayerTitle.WOMAN_GRANDMASTER:
                return "gf"
            case PlayerTitle.GRANDMASTER:
                return "g"
            case _:
                raise ValueError(f"Unknown title: {self}")

    @classmethod
    def from_fide_value(cls, value: str) -> Self:
        match value.strip():
            case "":
                return PlayerTitle.NONE
            case "WCM":
                return PlayerTitle.WOMAN_CANDIDATE_MASTER
            case "CM":
                return PlayerTitle.CANDIDATE_MASTER
            case "WFM":
                return PlayerTitle.WOMAN_FIDE_MASTER
            case "FM":
                return PlayerTitle.FIDE_MASTER
            case "WIM":
                return PlayerTitle.WOMAN_INTERNATIONAL_MASTER
            case "IM":
                return PlayerTitle.INTERNATIONAL_MASTER
            case "WGM":
                return PlayerTitle.WOMAN_GRANDMASTER
            case "GM":
                return PlayerTitle.GRANDMASTER
            case _:
                raise ValueError(f"Unknown title value: {value}")

    @property
    def to_trf(self) -> str:
        match self:
            case PlayerTitle.NONE:
                return ""
            case PlayerTitle.WOMAN_CANDIDATE_MASTER:
                return "cf"
            case PlayerTitle.CANDIDATE_MASTER:
                return "c"
            case PlayerTitle.WOMAN_FIDE_MASTER:
                return "ff"
            case PlayerTitle.FIDE_MASTER:
                return "f"
            case PlayerTitle.WOMAN_INTERNATIONAL_MASTER:
                return "mf"
            case PlayerTitle.INTERNATIONAL_MASTER:
                return "m"
            case PlayerTitle.WOMAN_GRANDMASTER:
                return "gf"
            case PlayerTitle.GRANDMASTER:
                return "g"
            case _:
                raise ValueError(f"Unknown title: {self}")

    @property
    def name(self) -> str:
        match self:
            case PlayerTitle.NONE:
                return _("No title")
            case PlayerTitle.WOMAN_CANDIDATE_MASTER:
                return _("Woman Candidate Master")
            case PlayerTitle.CANDIDATE_MASTER:
                return _("Candidate Master")
            case PlayerTitle.WOMAN_FIDE_MASTER:
                return _("Woman Fide Master")
            case PlayerTitle.FIDE_MASTER:
                return _("Fide Master")
            case PlayerTitle.WOMAN_INTERNATIONAL_MASTER:
                return _("Woman International Master")
            case PlayerTitle.INTERNATIONAL_MASTER:
                return _("International Master")
            case PlayerTitle.WOMAN_GRANDMASTER:
                return _("Woman Grand Master")
            case PlayerTitle.GRANDMASTER:
                return _("Grand Master")
            case _:
                raise ValueError(f"Unknown title: {self}")

    @property
    def short_name(self) -> str:
        match self:
            case PlayerTitle.NONE:
                return ""
            case PlayerTitle.WOMAN_CANDIDATE_MASTER:
                return _("WCM *** SHORT NAME FOR Woman Candidate Master")
            case PlayerTitle.CANDIDATE_MASTER:
                return _("CM *** SHORT NAME FOR Candidate Master")
            case PlayerTitle.WOMAN_FIDE_MASTER:
                return _("WFM *** SHORT NAME FOR Woman Fide Master")
            case PlayerTitle.FIDE_MASTER:
                return _("FM *** SHORT NAME FOR Fide Master")
            case PlayerTitle.WOMAN_INTERNATIONAL_MASTER:
                return _("WIM *** SHORT NAME FOR Woman International Master")
            case PlayerTitle.INTERNATIONAL_MASTER:
                return _("IM *** SHORT NAME FOR International Master")
            case PlayerTitle.WOMAN_GRANDMASTER:
                return _("WGM *** SHORT NAME FOR Woman Grand Master")
            case PlayerTitle.GRANDMASTER:
                return _("GM *** SHORT NAME FOR Grand Master")
            case _:
                raise ValueError(f"Unknown title: {self}")

    def __str__(self) -> str:
        return self.short_name


class BoardColor(StrEnum):
    WHITE = "W"
    BLACK = "B"

    @classmethod
    def from_papi_value(cls, value: str) -> Self:
        """Decode the database value"""
        match value:
            case "B":
                return BoardColor.WHITE
            case "N":
                return BoardColor.BLACK
            case _:
                raise ValueError(f"Unknown value: {value}")

    @property
    def to_papi_value(self) -> str:
        match self:
            case BoardColor.WHITE:
                return "B"
            case BoardColor.BLACK:
                return "N"
            case _:
                raise ValueError(f"Unknown value:  {self}")

    @property
    def to_trf(self) -> str:
        match self:
            case BoardColor.WHITE:
                return "w"
            case BoardColor.BLACK:
                return "b"
            case _:
                raise ValueError(f"Unknown value:  {self}")

    @property
    def to_trf_first_round_pairing(self) -> str:
        match self:
            case BoardColor.WHITE:
                return "white1"
            case BoardColor.BLACK:
                return "black1"
            case _:
                raise ValueError(f"Unknown value:  {self}")

    def __str__(self) -> str:
        match self:
            case BoardColor.WHITE:
                return _("White")
            case BoardColor.BLACK:
                return _("Black")
            case _:
                raise ValueError(f"Unknown value: {self}")


class ScreenType(StrEnum):
    Boards = auto()
    Input = auto()
    Players = auto()
    Results = auto()
    Image = auto()

    def __str__(self) -> str:
        match self:
            case ScreenType.Boards:
                return _("Pairings by board")
            case ScreenType.Input:
                return _("Results entry")
            case ScreenType.Players:
                return _("Parings by player")
            case ScreenType.Results:
                return _("Last results")
            case ScreenType.Image:
                return _("Image")
            case _:
                raise ValueError(f"Invalid screen type: {self}")

    @property
    def default_screen_name(self) -> str:
        return str(self)

    @classmethod
    def from_str(cls, value: str) -> Self:
        match value:
            case "boards":
                return cls.Boards
            case "input":
                return cls.Input
            case "players":
                return cls.Players
            case "results":
                return cls.Results
            case "image":
                return cls.Image
            case _:
                raise ValueError(f"Invalid screen type: {value}")

    def to_str(self) -> Self:
        match self:
            case self.Boards:
                return "boards"
            case self.Input:
                return "input"
            case self.Players:
                return "players"
            case self.Results:
                return "results"
            case self.Image:
                return "image"
            case _:
                raise ValueError(f"Invalid screen type: {self}")

    @property
    def icon_str(self) -> str:
        match self:
            case self.Boards:
                return "bi-card-list"
            case self.Input:
                return "bi-pencil-fill"
            case self.Players:
                return "bi-people-fill"
            case self.Results:
                return "bi-trophy-fill"
            case self.Image:
                return "bi-image"
            case _:
                raise ValueError(f"Invalid screen type: {self}")


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
                raise ValueError(f"Unknown value: {self}")


class TrfType(StrEnum):
    PAIRING = "PAIRING"
    RATING = "RATING"

    @property
    def file_extension(self) -> str:
        match self:
            case TrfType.RATING:
                return "trf"
            case TrfType.PAIRING:
                return "trfx"
            case _:
                raise ValueError(f"Unknown value: {self}")
