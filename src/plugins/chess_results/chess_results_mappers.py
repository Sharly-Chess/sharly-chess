from dataclasses import dataclass
from typing import Self

from data.pairings import PairingSystem
from data.pairings.systems import SwissPairingSystem, RoundRobinPairingSystem
from data.tie_breaks import TieBreak, tie_breaks as tb
from data.tie_breaks.cutters import TieBreakCutter
from data.tournament import Tournament, TournamentRating
from plugins.ffe import ffe_tie_breaks as ffe_tb
from plugins.ffe.ffe_tie_breaks import PapiBuchholzType
from utils import CoreMapper
from utils.enum import (
    PlayerGender,
)


class ChessResultsPlayerGender(CoreMapper[str, PlayerGender]):
    @classmethod
    def _core_object_by_outer_value(cls) -> dict[str, PlayerGender]:
        return {
            '': PlayerGender.NONE,
            'M': PlayerGender.MALE,
            'W': PlayerGender.FEMALE,
        }


class ChessResultPairingSystem(CoreMapper[str, PairingSystem]):
    @classmethod
    def _core_object_by_outer_value(cls) -> dict[str, PairingSystem]:
        return {
            '0': SwissPairingSystem(),
            '1': RoundRobinPairingSystem(),
        }


class ChessResultTournamentRating(CoreMapper[str, TournamentRating]):
    @classmethod
    def _core_object_by_outer_value(cls) -> dict[str, TournamentRating]:
        return {
            '1': TournamentRating.STANDARD,
            '2': TournamentRating.RAPID,
            '3': TournamentRating.BLITZ,
        }


@dataclass
class ChessResultsTieBreak:
    number: int
    param1: str = ''
    param2: str = ''
    param3: str = ''
    param4: str = ''
    param5: str = ''

    @property
    def params_str(self) -> str:
        return ','.join(
            (self.param1, self.param2, self.param3, self.param4, self.param5)
        )

    @classmethod
    def from_tie_break(cls, tournament: Tournament, tie_break: TieBreak) -> Self:
        """Mapping from our tie-breaks to the ones used by the Chess-Results
        (id + up to 5 parameters, see /docs/chess-results/Tie-Breaks.xlsx)"""
        match type(tie_break):
            case tb.WinsTieBreak:
                return cls(68)
            case tb.GamesWonTieBreak:
                # Closest, matches 'Wins'
                return cls(68)

            # 'Most black': Ambiguous, and marked as `Old / rarely used / not visible by default`
            case tb.GamesPlayedWithBlackTieBreak:
                return cls(53)
            case tb.GamesWonWithBlackTieBreak:
                return cls(53)

            case tb.ProgressiveScoresTieBreak:
                return cls(86)
            case tb.RoundsElectedToPlayTieBreak:
                return cls(79)
            case tb.StandardBuchholzTieBreak:
                return cls(
                    84,
                    param1='0',
                    **cls.cutter_params(tie_break),
                    param4=cls.played_param(tie_break),
                    param5='-',
                )
            case ffe_tb.PapiBuchholzTieBreak:
                buchholz_type: PapiBuchholzType = getattr(tie_break, 'type')
                cut = str(
                    ffe_tb.PapiBuchholzTieBreak.papi_buchholz_cut(tournament.rounds)
                )
                return cls(
                    84,
                    param1='0',
                    param2=cut if buchholz_type.use_top_cut else '0',
                    param3=cut if buchholz_type.use_bottom_cut else '0',
                    param4='-',
                    param5='-',
                )
            case tb.ForeBuchholzTieBreak:
                return cls(
                    84,
                    param1='0',
                    **cls.cutter_params(tie_break),
                    param4=cls.played_param(tie_break),
                    param5='F',
                )
            case tb.SumOfBuchholzTieBreak:
                return cls(25)
            case ffe_tb.PapiSumOfBuchholzTieBreak:
                return cls(25)
            case tb.AverageOfBuchholzTieBreak:
                return cls(77, 'F' if getattr(tie_break, 'fore_modifier') else '-')
            case tb.SonnebornBergerTieBreak:
                return cls(
                    85,
                    param1='0',
                    **cls.cutter_params(tie_break),
                    param4=cls.played_param(tie_break),
                    param5='-',
                )
            case tb.KoyaTieBreak:
                # Limit not passed, because we define it not as a percentage
                # but as half points above or below the 50% limit (as done in TRF25)
                return cls(87, '0', '50')
            case tb.KashdanTieBreak:
                return cls(92)
            case ffe_tb.PapiKashdanTieBreak:
                return cls(92, '0', '0')
            case tb.AverageRatingOpponentsTieBreak:
                return cls(80, param1='0', **cls.cutter_params(tie_break))
            case tb.TournamentPerformanceRatingTieBreak:
                return cls(88, '0', '0')
            case ffe_tb.PapiPerformanceTieBreak:
                return cls(88, '0', '0')
            case tb.AveragePerformanceRatingOpponentsTieBreak:
                return cls(88, '1', '0')
            case tb.PerfectTournamentPerformanceTieBreak:
                return cls(88, '2', '0')
            case tb.AveragePerfectPerformanceTieBreak:
                return cls(88, '3', '0')
            case tb.DirectEncounterTieBreak:
                return cls(81, cls.played_param(tie_break))
            case tb.ManualTieBreak:
                return cls(6)

        raise NotImplementedError(
            f'Chess-Results conversion not implemented for tie-break [{tie_break.id}]'
        )

    @staticmethod
    def cutter_params(tie_break: TieBreak) -> dict[str, str]:
        cutter: TieBreakCutter = getattr(tie_break, 'cutter')
        return {
            'param2': str(cutter.top_cut),
            'param3': str(cutter.bottom_cut),
        }

    @staticmethod
    def played_param(tie_break: TieBreak) -> str:
        return 'P' if getattr(tie_break, 'played_modifier') else '-'
