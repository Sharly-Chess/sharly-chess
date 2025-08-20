from dataclasses import dataclass
from enum import StrEnum, IntEnum
from typing import Self

from data.pairing import Pairing
from data.pairings import PairingVariation, variations
from data.pairings.systems import (
    RoundRobinPairingSystem,
    SwissPairingSystem,
    PairingSystem,
)
from data.tie_breaks import tie_breaks, TieBreak
from plugins.ffe import ffe_tie_breaks
from plugins.ffe.utils import PlayerFFELicence
from plugins.pairing_acceleration import pairing_variations as accelerations
from plugins.utils import PluginCoreMapper
from utils.enum import (
    TournamentRating,
    PlayerGender,
    PlayerTitle,
    PlayerCategory,
    PlayerRatingType,
    Result,
    BoardColor,
)


class PapiPairingVariation(PluginCoreMapper[str, PairingVariation]):
    """Mapper of the pairing variations in the Papi database."""

    @classmethod
    def _core_object_by_plugin_value(cls) -> dict[str, PairingVariation]:
        from plugins.ffe.ffe_entity import NicoisSwissVariation

        return {
            'Standard': variations.StandardSwissVariation(),
            'Haley': accelerations.HaleySwissVariation(),
            'HaleySoft': accelerations.HaleySoftSwissVariation(),
            'SAD': accelerations.ProgressiveSwissVariation(),
            'Nicois': NicoisSwissVariation(),
            'Berger': variations.BergerRoundRobinVariation(),
        }

    @classmethod
    def get_plugin_value(cls, core_object: PairingVariation) -> str | None:
        if core_object == variations.DoubleBergerRoundRobinVariation():
            core_object = variations.BergerRoundRobinVariation()
        return super().get_plugin_value(core_object)


class PapiPairingSystem(PluginCoreMapper[str, PairingSystem]):
    @staticmethod
    def _core_object_by_plugin_value() -> dict[str, PairingSystem]:
        return {
            'Suisse': SwissPairingSystem(),
            'ToutesRondes': RoundRobinPairingSystem(),
        }


class PapiTieBreak(PluginCoreMapper[str, TieBreak]):
    @classmethod
    def _core_object_by_plugin_value(cls) -> dict[str, TieBreak]:
        return {
            'Solkoff': ffe_tie_breaks.PapiStandardBuchholzTieBreak(),
            'Brésilien': ffe_tie_breaks.PapiBuchholzCutBottomTieBreak(),
            'Harkness': ffe_tie_breaks.PapiMedianBuchholzTieBreak(),
            'Cumulatif': tie_breaks.ProgressiveScoresTieBreak(),
            'Performance': ffe_tie_breaks.PapiPerformanceTieBreak(),
            'SommeDesBuchholz': ffe_tie_breaks.PapiSumOfBuchholzTieBreak(),
            'Kashdan': ffe_tie_breaks.PapiKashdanTieBreak(),
            'Nombre de Victoires': tie_breaks.WinsTieBreak(),
            'Sonnenborn-Berger': tie_breaks.SonnebornBergerTieBreak(),
            'Koya': tie_breaks.KoyaTieBreak(),
        }


class PapiTournamentRating(PluginCoreMapper[str, TournamentRating]):
    @staticmethod
    def _core_object_by_plugin_value() -> dict[str, TournamentRating]:
        return {
            'Elo': TournamentRating.STANDARD,
            'Rapide': TournamentRating.RAPID,
            'Blitz': TournamentRating.BLITZ,
        }


class PapiPlayerGender(PluginCoreMapper[str, PlayerGender]):
    @classmethod
    def _core_object_by_plugin_value(cls) -> dict[str, PlayerGender]:
        return {
            '': PlayerGender.NONE,
            'M': PlayerGender.MALE,
            'F': PlayerGender.FEMALE,
        }

    @classmethod
    def get_core_object(cls, plugin_value: str) -> PlayerGender:
        return cls._core_object_by_plugin_value()[plugin_value.upper()]


class PapiThreePointsForAWin(PluginCoreMapper[str, bool]):
    @classmethod
    def _core_object_by_plugin_value(cls) -> dict[str, bool]:
        return {
            'OUI': True,
            'NON': False,
        }

    @classmethod
    def get_core_object(cls, plugin_value: str) -> bool:
        return cls._core_object_by_plugin_value()[plugin_value.upper()]


class PapiPlayerTitle(PluginCoreMapper[str, PlayerTitle]):
    @classmethod
    def _core_object_by_plugin_value(cls) -> dict[str, PlayerTitle]:
        return {
            '': PlayerTitle.NONE,
            'c': PlayerTitle.NONE,
            'cf': PlayerTitle.NONE,
            'ff': PlayerTitle.WOMAN_FIDE_MASTER,
            'f': PlayerTitle.FIDE_MASTER,
            'mf': PlayerTitle.WOMAN_INTERNATIONAL_MASTER,
            'm': PlayerTitle.INTERNATIONAL_MASTER,
            'gf': PlayerTitle.WOMAN_GRANDMASTER,
            'g': PlayerTitle.GRANDMASTER,
        }

    @classmethod
    def get_core_object(cls, plugin_value: str) -> PlayerTitle:
        return cls._core_object_by_plugin_value()[plugin_value.strip()]


class PapiPlayerCategory(PluginCoreMapper[str, PlayerCategory]):
    @staticmethod
    def _core_object_by_plugin_value() -> dict[str, PlayerCategory]:
        return {
            '': PlayerCategory.NONE,
            'Ppo': PlayerCategory.U8,
            'Pou': PlayerCategory.U10,
            'Pup': PlayerCategory.U12,
            'Ben': PlayerCategory.U14,
            'Min': PlayerCategory.U16,
            'Cad': PlayerCategory.U18,
            'Jun': PlayerCategory.U20,
            'Sen': PlayerCategory.O20,
            'Sep': PlayerCategory.O50,
            'Vet': PlayerCategory.O65,
        }


class PapiPlayerRatingType(PluginCoreMapper[str | None, PlayerRatingType]):
    @staticmethod
    def _core_object_by_plugin_value() -> dict[str | None, PlayerRatingType]:
        return {
            'E': PlayerRatingType.ESTIMATED,
            'N': PlayerRatingType.NATIONAL,
            'F': PlayerRatingType.FIDE,
        }

    @classmethod
    def get_core_object(cls, plugin_value: str | None) -> PlayerRatingType:
        if plugin_value is None:
            return PlayerRatingType.ESTIMATED
        return super().get_core_object(plugin_value)


class PapiPlayerFFELicence(PluginCoreMapper[str, PlayerFFELicence]):
    @staticmethod
    def _core_object_by_plugin_value() -> dict[str, PlayerFFELicence]:
        return {
            '': PlayerFFELicence.NONE,
            'N': PlayerFFELicence.N,
            'A': PlayerFFELicence.A,
            'B': PlayerFFELicence.B,
        }


class PapiColor(StrEnum):
    WHITE = 'B'
    BLACK = 'N'
    UNPAIRED = 'R'
    BYE = 'F'


class PapiResult(IntEnum):
    UNPLAYED_OR_NOT_PAIRED = 0
    LOSS = 1
    DRAW_OR_HPB = 2  # HPB = Half-Point Bye
    GAIN = 3
    FORFEIT_LOSS = 4
    DOUBLE_FORFEIT = 5
    PAB_OR_FORFEIT_GAIN_OR_FPB = 6  # PAB = Pairing-Allocated-Bye, FPB = Full-Point Bye


@dataclass
class PapiRound:
    color: PapiColor
    opponent: int | None = None
    result: PapiResult = PapiResult.UNPLAYED_OR_NOT_PAIRED

    def to_result(self, is_round_robin: bool = False) -> Result:
        match self.result:
            case PapiResult.UNPLAYED_OR_NOT_PAIRED:
                if self.color == PapiColor.BYE:
                    return Result.ZERO_POINT_BYE
                if is_round_robin and self.opponent is None:
                    return Result.REST_GAME
                return Result.NO_RESULT
            case PapiResult.LOSS:
                return Result.LOSS
            case PapiResult.DRAW_OR_HPB:
                if self.color == PapiColor.BYE:
                    return Result.HALF_POINT_BYE
                return Result.DRAW
            case PapiResult.GAIN:
                return Result.GAIN
            case PapiResult.FORFEIT_LOSS:
                return Result.FORFEIT_LOSS
            case PapiResult.DOUBLE_FORFEIT:
                return Result.DOUBLE_FORFEIT
            case PapiResult.PAB_OR_FORFEIT_GAIN_OR_FPB:
                if self.color == PapiColor.BYE:
                    return Result.FULL_POINT_BYE
                if self.opponent is not None:
                    return Result.FORFEIT_GAIN
                return Result.PAIRING_ALLOCATED_BYE
            case _:
                raise ValueError(f'Unknown value: {self.result}')

    @classmethod
    def from_pairing(cls, pairing: Pairing) -> Self:
        papi_color: PapiColor | None
        if (
            pairing.result == Result.NO_RESULT and not pairing.board
        ) or pairing.result == Result.REST_GAME:
            papi_color = PapiColor.UNPAIRED
        elif pairing.color == BoardColor.WHITE:
            papi_color = PapiColor.WHITE
        elif pairing.color == BoardColor.BLACK:
            papi_color = PapiColor.BLACK
        else:
            papi_color = PapiColor.BYE
        return cls(
            papi_color,
            pairing.opponent_id,
            cls._result_to_papi_result(pairing.result),
        )

    @staticmethod
    def _result_to_papi_result(result: Result):
        match result:
            case Result.GAIN | Result.UNRATED_GAIN:
                return PapiResult.GAIN
            case Result.LOSS | Result.UNRATED_LOSS:
                return PapiResult.LOSS
            case Result.DRAW | Result.UNRATED_DRAW | Result.HALF_POINT_BYE:
                return PapiResult.DRAW_OR_HPB
            case Result.NO_RESULT | Result.ZERO_POINT_BYE | Result.REST_GAME:
                return PapiResult.UNPLAYED_OR_NOT_PAIRED
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
                raise ValueError(f'Unknown value: {result}')
