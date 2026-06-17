from dataclasses import dataclass
from typing import Self

from data.pairings import PairingSystem
from data.pairings.systems import (
    RoundRobinPairingSystem,
    SwissPairingSystem,
    TeamRoundRobinPairingSystem,
    TeamSwissPairingSystem,
    TeamTwoGameMatchPairingSystem,
)
from data.tie_breaks import TieBreak, tie_breaks as tb
from data.tie_breaks import team_tie_breaks as ttb
from data.tie_breaks.team_tie_breaks import ESBVariant
from data.tie_breaks.cutters import TieBreakCutter
from data.tournament import Tournament, TournamentRating
from plugins.ffe import ffe_tie_breaks as ffe_tb
from plugins.ffe.ffe_tie_breaks import PapiBuchholzType
from utils import CoreMapper
from utils.enum import (
    PlayerGender,
    Result,
    ScoreType,
)


class ChessResultsPlayerGender(CoreMapper[str, PlayerGender]):
    @classmethod
    def _core_object_by_outer_value(cls) -> dict[str, PlayerGender]:
        return {
            '': PlayerGender.NONE,
            'M': PlayerGender.MAN,
            'W': PlayerGender.WOMAN,
        }


class ChessResultPairingSystem(CoreMapper[tuple[str, str], PairingSystem]):
    """Pairing system to Chess-Results ``(type, replay)``. The type code
    alone is not unique: team round-robin and team two-game match are both
    type ``2``, distinguished by the replay count."""

    @classmethod
    def _core_object_by_outer_value(cls) -> dict[tuple[str, str], PairingSystem]:
        return {
            ('0', '1'): SwissPairingSystem(),
            ('1', '1'): RoundRobinPairingSystem(),
            ('3', '1'): TeamSwissPairingSystem(),
            ('2', '1'): TeamRoundRobinPairingSystem(),
            ('2', '2'): TeamTwoGameMatchPairingSystem(),
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
        (id + up to 5 parameters, see /docs/technical-appendices/chess-results/Tie-Breaks-1.xlsx)"""
        match type(tie_break):
            # Victories (variable): Type 0..WIN, 1..WON, 2..BWG (games won
            # with black), 3..BPG (games played with black) + played
            # modifier.
            case tb.WinsTieBreak:
                return cls(68, param1='0', param2=cls.played_param(tie_break))
            case tb.GamesWonTieBreak:
                return cls(68, param1='1', param2=cls.played_param(tie_break))
            case tb.GamesWonWithBlackTieBreak:
                return cls(68, param1='2', param2=cls.played_param(tie_break))
            case tb.GamesPlayedWithBlackTieBreak:
                return cls(68, param1='3', param2=cls.played_param(tie_break))

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
                return cls(5)
            case (
                tb.StandardPointsTieBreak
                | tb.PairingNumberTieBreak
                | tb.PlayerRatingTieBreak
            ):
                # TODO (Molrn) Contact CR admin to add codes for those
                return cls(5)
            case ttb.MatchPointsVsGamePointsTieBreak:
                # The secondary score: matchpoints (13) when the primary
                # is game points, plain game points (1) otherwise.
                return cls(
                    1 if tournament.primary_score == ScoreType.MATCH_POINTS else 13
                )
            case ttb.ExtendedSonnebornBergerTeamTieBreak:
                variant_index = {
                    ESBVariant.EMMSB: '0',
                    ESBVariant.EMGSB: '1',
                    ESBVariant.EGMSB: '2',
                    ESBVariant.EGGSB: '3',
                }[getattr(tie_break, 'variant')]
                return cls(
                    82,
                    param1=variant_index,
                    **cls.cutter_params(tie_break),
                    param4=cls.played_param(tie_break),
                    param5=cls.mp_calc_param(tournament),
                )
            case ttb.ScoresAndScheduleStrengthCombinationTieBreak:
                return cls(
                    91,
                    param1=cls.primary_score_param(tournament),
                    param2=cls.played_param(tie_break),
                )
            case ttb.ExtendedDirectEncounterTieBreak:
                return cls(
                    83,
                    param1=cls.primary_score_param(tournament),
                    param2=cls.played_param(tie_break),
                )
            case ffe_tb.BerlinTieBreak:
                return cls(71)
            case ffe_tb.GamePointsForTieBreak:
                return cls(1)
            case (
                ffe_tb.GamePointsDifferentialTieBreak
                | ffe_tb.LowestOwnAverageRatingTieBreak
            ):
                # No Chess-Results codes for these; ``5`` (manual /
                # informative) keeps the export valid with our values.
                return cls(5)

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
        return 'P' if getattr(tie_break, 'played_modifier', False) else '-'

    @staticmethod
    def primary_score_param(tournament: Tournament) -> str:
        """``GP`` / ``MP`` parameter of the team tie-breaks that follow
        the tournament's primary score."""
        return 'MP' if tournament.primary_score == ScoreType.MATCH_POINTS else 'GP'

    @staticmethod
    def mp_calc_param(tournament: Tournament) -> str:
        """Chess-Results 'MP calc' parameter: ``0`` for 2/1/0 match
        points, ``1`` for 3/1/0."""
        return '1' if tournament.match_points.get(Result.WIN) == 3 else '0'
