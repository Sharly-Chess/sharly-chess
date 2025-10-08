from typing import ClassVar, Optional, Union
from data.tie_breaks import TieBreak, tie_breaks
from plugins.ffe import ffe_tie_breaks
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


class ChessResultsTieBreak:
    mapping: ClassVar[dict[type[TieBreak], tuple[str, str, str, str, str]]] = {
        tie_breaks.StandardBuchholzTieBreak: ('2', '', '', '', ''),
        tie_breaks.ManualTieBreak: ('5', '', '', '', ''),
        tie_breaks.SonnebornBergerTieBreak: ('7', '', '', '', ''),
        tie_breaks.ForeBuchholzTieBreak: ('8', '', '', '', ''),
        tie_breaks.DirectEncounterTieBreak: ('11', '', '', '', ''),
        tie_breaks.GamesWonTieBreak: ('12', '', '', '', ''),
        tie_breaks.WinsTieBreak: ('12', '', '', '', ''),
        tie_breaks.SumOfBuchholzTieBreak: ('25', '', '', '', ''),
        tie_breaks.GamesPlayedWithBlackTieBreak: ('53', '', '', '', ''),
        tie_breaks.GamesWonWithBlackTieBreak: ('53', '', '', '', ''),
        tie_breaks.KoyaTieBreak: ('69', '', '', '', ''),
        tie_breaks.RoundsElectedToPlayTieBreak: ('79', '', '', '', ''),
        tie_breaks.AverageOfBuchholzTieBreak: ('77', '', '', '', ''),
        tie_breaks.AverageRatingOpponentsTieBreak: ('80', '', '', '', ''),
        tie_breaks.ProgressiveScoresTieBreak: ('86', '', '', '', ''),
        tie_breaks.TournamentPerformanceRatingTieBreak: ('88', '0', '', '', ''),
        tie_breaks.AveragePerformanceRatingOpponentsTieBreak: ('88', '1', '', '', ''),
        tie_breaks.PerfectTournamentPerformanceTieBreak: ('88', '2', '', '', ''),
        tie_breaks.AveragePerfectPerformanceTieBreak: ('88', '3', '', '', ''),
        ffe_tie_breaks.PapiStandardBuchholzTieBreak: ('2', '', '', '', ''),
        ffe_tie_breaks.PapiBuchholzCutBottomTieBreak: ('3', '', '', '', ''),
        ffe_tie_breaks.PapiMedianBuchholzTieBreak: ('4', '', '', '', ''),
        ffe_tie_breaks.PapiSumOfBuchholzTieBreak: ('25', '', '', '', ''),
        ffe_tie_breaks.PapiPerformanceTieBreak: ('88', '0', '', '', ''),
    }

    @classmethod
    def data_for_tiebreak(
        cls, tb: Union[TieBreak, type[TieBreak]]
    ) -> Optional[tuple[str, str, str, str, str]]:
        """
        Given a TieBreak instance or class, return the Chess-Results tuple
        (key, param1, param2, param3, param4). Returns None if not found.
        """
        tb_class = tb if isinstance(tb, type) else type(tb)
        return cls.mapping.get(tb_class)
