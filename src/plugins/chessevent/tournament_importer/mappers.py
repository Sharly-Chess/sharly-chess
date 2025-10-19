from data.pairings import PairingSystem, PairingVariation
from data.pairings.systems import SwissPairingSystem, RoundRobinPairingSystem
from data.pairings.variations import StandardSwissVariation, BergerRoundRobinVariation
from data.tie_breaks import TieBreak, tie_breaks
from plugins.ffe import ffe_tie_breaks
from plugins.ffe.ffe_entity import NicoisSwissVariation
from plugins.ffe.ffe_tie_breaks import (
    PapiBuchholzTypeOption,
    StandardPapiBuchholzType,
    CutPapiBuchholzType,
    MedianPapiBuchholzType,
)
from plugins.ffe.utils import PlayerFFELicence
from plugins.pairing_acceleration.pairing_variations import (
    HaleySwissVariation,
    HaleySoftSwissVariation,
    ProgressiveSwissVariation,
)
from utils import CoreMapper
from utils.enum import PlayerRatingType, PlayerTitle


class ChessEventPairingSystem(CoreMapper[int, PairingSystem]):
    @staticmethod
    def _core_object_by_outer_value() -> dict[int, PairingSystem]:
        return {
            1: SwissPairingSystem(),
            2: RoundRobinPairingSystem(),
        }


class ChessEventPairingVariation(CoreMapper[int, PairingVariation]):
    @staticmethod
    def _core_object_by_outer_value() -> dict[int, PairingVariation]:
        return {
            1: StandardSwissVariation(),
            2: HaleySwissVariation(),
            3: HaleySoftSwissVariation(),
            4: ProgressiveSwissVariation(),
            5: NicoisSwissVariation(),
            6: BergerRoundRobinVariation(),
        }


class ChessEventTieBreak(CoreMapper[int, TieBreak]):
    @staticmethod
    def _core_object_by_outer_value() -> dict[int, TieBreak]:
        return {
            1: ffe_tie_breaks.PapiBuchholzTieBreak(
                [PapiBuchholzTypeOption(StandardPapiBuchholzType().id)]
            ),
            2: ffe_tie_breaks.PapiBuchholzTieBreak(
                [PapiBuchholzTypeOption(CutPapiBuchholzType().id)]
            ),
            3: ffe_tie_breaks.PapiBuchholzTieBreak(
                [PapiBuchholzTypeOption(MedianPapiBuchholzType().id)]
            ),
            4: tie_breaks.ProgressiveScoresTieBreak(),
            5: ffe_tie_breaks.PapiPerformanceTieBreak(),
            6: ffe_tie_breaks.PapiSumOfBuchholzTieBreak(),
            7: tie_breaks.WinsTieBreak(),
            8: ffe_tie_breaks.PapiKashdanTieBreak(),
            9: tie_breaks.KoyaTieBreak(),
            10: tie_breaks.SonnebornBergerTieBreak(),
        }


class ChessEventFFELicence(CoreMapper[int, PlayerFFELicence]):
    @staticmethod
    def _core_object_by_outer_value() -> dict[int, PlayerFFELicence]:
        return {
            0: PlayerFFELicence.NONE,
            1: PlayerFFELicence.N,
            2: PlayerFFELicence.B,
            3: PlayerFFELicence.A,
        }


class ChessEventRatingType(CoreMapper[int, PlayerRatingType]):
    @staticmethod
    def _core_object_by_outer_value() -> dict[int, PlayerRatingType]:
        return {
            1: PlayerRatingType.ESTIMATED,
            2: PlayerRatingType.NATIONAL,
            3: PlayerRatingType.FIDE,
        }


class ChessEventTitle(CoreMapper[int, PlayerTitle]):
    @staticmethod
    def _core_object_by_outer_value() -> dict[int, PlayerTitle]:
        return {
            0: PlayerTitle.NONE,
            1: PlayerTitle.WOMAN_FIDE_MASTER,
            2: PlayerTitle.FIDE_MASTER,
            3: PlayerTitle.WOMAN_INTERNATIONAL_MASTER,
            4: PlayerTitle.INTERNATIONAL_MASTER,
            5: PlayerTitle.WOMAN_GRANDMASTER,
            6: PlayerTitle.GRANDMASTER,
        }
