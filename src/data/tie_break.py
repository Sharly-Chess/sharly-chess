from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from types import UnionType
from typing import Self, Any, Optional, TYPE_CHECKING

from common.i18n import _

if TYPE_CHECKING:
    from data.player import Player
    from data.tournament import Tournament


class PapiTieBreak(IntEnum):
    """An enumeration representing the supported types of tournament
    tie breaks in Papi."""

    NONE = 0
    BUCHHOLZ = 1
    BUCHHOLZ_CUT_BOTTOM = 2
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
            case '':
                return cls.NONE
            case 'Solkoff':
                return cls.BUCHHOLZ
            case 'Brésilien':
                return cls.BUCHHOLZ_CUT_BOTTOM
            case 'Harkness':
                return cls.BUCHHOLZ_CUT_TOP_BOTTOM
            case 'Cumulatif':
                return cls.CUMULATIVE
            case 'Performance':
                return cls.PERFORMANCE
            case 'SommeDesBuchholz':
                return cls.BUCHHOLZ_SUM
            case 'Nombre de Victoires':
                return cls.WINS
            case 'Kashdan':
                return cls.KASHDAN
            case 'Koya':
                return cls.KOYA
            case 'Sonnenborn-Berger':
                return cls.SONNENBORN_BERGER
            case _:
                raise ValueError(f'Unknown value: {value}')

    @property
    def to_papi_value(self) -> str:
        match self:
            case PapiTieBreak.NONE:
                return ''
            case PapiTieBreak.BUCHHOLZ:
                return 'Solkoff'
            case PapiTieBreak.BUCHHOLZ_CUT_BOTTOM:
                return 'Brésilien'
            case PapiTieBreak.BUCHHOLZ_CUT_TOP_BOTTOM:
                return 'Harkness'
            case PapiTieBreak.CUMULATIVE:
                return 'Cumulatif'
            case PapiTieBreak.PERFORMANCE:
                return 'Performance'
            case PapiTieBreak.BUCHHOLZ_SUM:
                return 'SommeDesBuchholz'
            case PapiTieBreak.WINS:
                return 'Nombre de Victoires'
            case PapiTieBreak.KASHDAN:
                return 'Kashdan'
            case PapiTieBreak.KOYA:
                return 'Koya'
            case PapiTieBreak.SONNENBORN_BERGER:
                return 'Sonnenborn-Berger'
            case _:
                raise ValueError(f'Unknown tie break: {self}')

    def to_tie_break(self, tournament_rounds: int) -> Optional['TieBreak']:
        match self:
            case PapiTieBreak.NONE:
                return None
            case PapiTieBreak.BUCHHOLZ:
                return TieBreak(
                    TieBreakType.BUCHHOLZ,
                    {TieBreakOption.PAPI_LEGACY: True}
                )
            case PapiTieBreak.BUCHHOLZ_CUT_BOTTOM:
                return TieBreak(
                    TieBreakType.BUCHHOLZ,
                    {
                        TieBreakOption.CUT_BOTTOM: (
                            self._papi_buchholz_cut(tournament_rounds)
                        ),
                        TieBreakOption.PAPI_LEGACY: True,
                    }
                )
            case PapiTieBreak.BUCHHOLZ_CUT_TOP_BOTTOM:
                buchholz_cut = self._papi_buchholz_cut(tournament_rounds)
                return TieBreak(
                    TieBreakType.BUCHHOLZ,
                    {
                        TieBreakOption.CUT_TOP: buchholz_cut,
                        TieBreakOption.CUT_BOTTOM: buchholz_cut,
                        TieBreakOption.PAPI_LEGACY: True,
                    },
                )
            case PapiTieBreak.PERFORMANCE:
                return TieBreak(
                    TieBreakType.TOURNAMENT_PERFORMANCE_RATING,
                    {TieBreakOption.PAPI_LEGACY: True},
                )
            case PapiTieBreak.BUCHHOLZ_SUM:
                return TieBreak(
                    TieBreakType.SUM_OF_BUCHHOLZ,
                    {
                        TieBreakOption.FORE_MODIFIER: False,
                        TieBreakOption.PAPI_LEGACY: True,
                    },
                )
            case PapiTieBreak.WINS:
                return TieBreak(TieBreakType.WINS, {})
            case PapiTieBreak.KOYA:
                return TieBreak(TieBreakType.KOYA, {})
            case PapiTieBreak.SONNENBORN_BERGER:
                return TieBreak(TieBreakType.SONNENBORN_BERGER, {})
            case PapiTieBreak.CUMULATIVE:
                return TieBreak(TieBreakType.PROGRESSIVE_SCORES, {})
            case PapiTieBreak.KASHDAN:
                # TODO implement Kashdan tie break
                return None
            case _:
                raise ValueError(f'Unknown tie break: {self}')

    def _papi_buchholz_cut(self, tournament_rounds: int) -> int:
        if tournament_rounds <= 7:
            return 1
        elif tournament_rounds <= 12:
            return 2
        return 3
    
    @classmethod
    def from_tie_break(cls, tie_break: 'TieBreak') -> Self:
        match tie_break.type:
            case TieBreakType.BUCHHOLZ:
                if TieBreakOption.CUT_BOTTOM not in tie_break.options.keys():
                    return cls.BUCHHOLZ
                elif TieBreakOption.CUT_TOP not in tie_break.options.keys():
                    return cls.BUCHHOLZ_CUT_BOTTOM
                return cls.BUCHHOLZ_CUT_TOP_BOTTOM
            case TieBreakType.PROGRESSIVE_SCORES:
                return cls.CUMULATIVE
            case TieBreakType.TOURNAMENT_PERFORMANCE_RATING:
                return cls.PERFORMANCE
            case TieBreakType.SUM_OF_BUCHHOLZ:
                return cls.BUCHHOLZ_SUM
            case TieBreakType.WINS:
                return cls.WINS
            case TieBreakType.KOYA:
                return cls.KOYA
            case TieBreakType.SONNENBORN_BERGER:
                return cls.SONNENBORN_BERGER
            case _:
                return cls.NONE


class TieBreakOption(StrEnum):
    """An enumeration representing the options of the tie-break functions"""
    
    CUT = 'cut'
    CUT_TOP = 'cut_top'
    CUT_BOTTOM = 'cut_btm'
    PLAYED_MODIFIER = 'played_modifier'
    PAPI_LEGACY = 'papi_legacy'
    FORE_MODIFIER = 'fore_modifier'
    LIMIT = 'limit'
    EXCLUDE_IDS = 'exclude_ids'

    @property
    def type(self) -> type | UnionType:
        match self:
            case TieBreakOption.CUT:
                return int
            case TieBreakOption.CUT_TOP:
                return int
            case TieBreakOption.CUT_BOTTOM:
                return int
            case TieBreakOption.PLAYED_MODIFIER:
                return bool
            case TieBreakOption.PAPI_LEGACY:
                return bool
            case TieBreakOption.FORE_MODIFIER:
                return bool
            case TieBreakOption.LIMIT:
                return float | None
            case TieBreakOption.EXCLUDE_IDS:
                return Iterable[int] | None
            case _:
                raise ValueError(f'Unknown tie break option: {self}')

    @property
    def name(self) -> str:
        match self:
            case TieBreakOption.CUT:
                return _('Cut')
            case TieBreakOption.CUT_TOP:
                return _('Cut top')
            case TieBreakOption.CUT_BOTTOM:
                return _('Cut Bottom')
            case TieBreakOption.PLAYED_MODIFIER:
                return _('Played modifier')
            case TieBreakOption.PAPI_LEGACY:
                return _('Papi legacy')
            case TieBreakOption.FORE_MODIFIER:
                return _('Fore modifier')
            case TieBreakOption.LIMIT:
                return _('Limit')
            case TieBreakOption.EXCLUDE_IDS:
                return _('Exclude players')
            case _:
                raise ValueError(f'Unknown tie break option: {self}')


class TieBreakType(StrEnum):
    """An enumeration representing the supported types of tournament
    tie breaks"""

    WINS = 'WINS'
    GAMES_WON = 'GAMES_WON'
    GAMES_PLAYED_WITH_BLACK = 'GAMES_PLAYED_WITH_BLACK'
    GAMES_WON_WITH_BLACK = 'GAMES_WON_WITH_BLACK'
    PROGRESSIVE_SCORES = 'PROGRESSIVE_SCORES'
    ROUNDS_ELECTED_TO_PLAY = 'ROUNDS_ELECTED_TO_PLAY'
    BUCHHOLZ = 'BUCHHOLZ'
    AVERAGE_OF_BUCHHOLZ = 'AVERAGE_OF_BUCHHOLZ'
    FORE_BUCHHOLZ = 'FORE_BUCHHOLZ'
    SUM_OF_BUCHHOLZ = 'SUM_OF_BUCHHOLZ'
    SONNENBORN_BERGER = 'SONNENBORN_BERGER'
    KOYA = 'KOYA'
    AVERAGE_RATING_OPPONENTS = 'AVERAGE_RATING_OPPONENTS'
    TOURNAMENT_PERFORMANCE_RATING = 'TOURNAMENT_PERFORMANCE_RATING'
    AVERAGE_PERFORMANCE_RATING_OPPONENTS = 'AVERAGE_PERFORMANCE_RATING_OPPONENTS'
    PERFECT_TOURNAMENT_PERFORMANCE = 'PERFECT_TOURNAMENT_PERFORMANCE'
    AVERAGE_PERFECT_PERFORMANCE = 'AVERAGE_PERFECT_PERFORMANCE'
    DIRECT_ENCOUNTER = 'DIRECT_ENCOUNTER'

    @property
    def name(self) -> str:
        match self:
            case TieBreakType.WINS:
                return _('Number of Wins')
            case TieBreakType.GAMES_WON:
                return _('Number of Games Won')
            case TieBreakType.GAMES_PLAYED_WITH_BLACK:
                return _('Number of Games Played with Black')
            case TieBreakType.GAMES_WON_WITH_BLACK:
                return _('Number of Games Won with Black')
            case TieBreakType.PROGRESSIVE_SCORES:
                return _('Progressive Scores')
            case TieBreakType.ROUNDS_ELECTED_TO_PLAY:
                return _('Rounds one Elected to Play')
            case TieBreakType.BUCHHOLZ:
                return _('Buchholz')
            case TieBreakType.AVERAGE_OF_BUCHHOLZ:
                return _('Average of Opponents Buchholz')
            case TieBreakType.FORE_BUCHHOLZ:
                return _('Fore Buchholz')
            case TieBreakType.SUM_OF_BUCHHOLZ:
                return _('Sum of Buchholz')
            case TieBreakType.SONNENBORN_BERGER:
                return _('Sonneborn-Berger')
            case TieBreakType.KOYA:
                return _('Koya System')
            case TieBreakType.AVERAGE_RATING_OPPONENTS:
                return _('Average Rating of Opponents')
            case TieBreakType.TOURNAMENT_PERFORMANCE_RATING:
                return _('Tournament Performance Rating')
            case TieBreakType.AVERAGE_PERFORMANCE_RATING_OPPONENTS:
                return _('Average Performance Rating of Opponents')
            case TieBreakType.PERFECT_TOURNAMENT_PERFORMANCE:
                return _('Perfect Tournament Performance')
            case TieBreakType.AVERAGE_PERFECT_PERFORMANCE:
                return _('Average Perfect Performance of Opponents')
            case TieBreakType.DIRECT_ENCOUNTER:
                return _('Direct Encounter')
            case _:
                raise ValueError(f'Unknown tie break: {self}')

    @property
    def compute_function(self) -> Callable:
        from tie_breaks import individual

        match self:
            case TieBreakType.WINS:
                return individual.wins
            case TieBreakType.GAMES_WON:
                return individual.games_won
            case TieBreakType.GAMES_PLAYED_WITH_BLACK:
                return individual.games_played_with_black
            case TieBreakType.GAMES_WON_WITH_BLACK:
                return individual.games_won_with_black
            case TieBreakType.PROGRESSIVE_SCORES:
                return individual.progressive_scores
            case TieBreakType.ROUNDS_ELECTED_TO_PLAY:
                return individual.rounds_elected_to_play
            case TieBreakType.BUCHHOLZ:
                return individual.buchholz
            case TieBreakType.AVERAGE_OF_BUCHHOLZ:
                return individual.average_of_buchholz
            case TieBreakType.FORE_BUCHHOLZ:
                return individual.fore_buchholz
            case TieBreakType.SUM_OF_BUCHHOLZ:
                return individual.sum_of_buchholz
            case TieBreakType.SONNENBORN_BERGER:
                return individual.sonneborn_berger
            case TieBreakType.KOYA:
                return individual.koya
            case TieBreakType.AVERAGE_RATING_OPPONENTS:
                return individual.average_rating_opponents
            case TieBreakType.TOURNAMENT_PERFORMANCE_RATING:
                return individual.tournament_performance_rating
            case TieBreakType.AVERAGE_PERFORMANCE_RATING_OPPONENTS:
                return individual.average_performance_rating_opponents
            case TieBreakType.PERFECT_TOURNAMENT_PERFORMANCE:
                return individual.perfect_tournament_performance
            case TieBreakType.AVERAGE_PERFECT_PERFORMANCE:
                return individual.average_perfect_performance
            case TieBreakType.DIRECT_ENCOUNTER:
                return individual.direct_encounter
            case _:
                raise ValueError(f'Unknown tie break: {self}')

    @property
    def acronym(self) -> str:
        match self:
            case TieBreakType.WINS:
                return 'WIN'
            case TieBreakType.GAMES_WON:
                return 'WON'
            case TieBreakType.GAMES_PLAYED_WITH_BLACK:
                return 'BPG'
            case TieBreakType.GAMES_WON_WITH_BLACK:
                return 'BWG'
            case TieBreakType.PROGRESSIVE_SCORES:
                return 'PS'
            case TieBreakType.ROUNDS_ELECTED_TO_PLAY:
                return 'REP'
            case TieBreakType.BUCHHOLZ:
                return 'BH'
            case TieBreakType.AVERAGE_OF_BUCHHOLZ:
                return 'AOB'
            case TieBreakType.FORE_BUCHHOLZ:
                return 'FB'
            case TieBreakType.SUM_OF_BUCHHOLZ:
                return 'SOB'
            case TieBreakType.SONNENBORN_BERGER:
                return 'SB'
            case TieBreakType.KOYA:
                return 'KS'
            case TieBreakType.AVERAGE_RATING_OPPONENTS:
                return 'ARO'
            case TieBreakType.TOURNAMENT_PERFORMANCE_RATING:
                return 'TPR'
            case TieBreakType.AVERAGE_PERFORMANCE_RATING_OPPONENTS:
                return 'APRO'
            case TieBreakType.PERFECT_TOURNAMENT_PERFORMANCE:
                return 'PTP'
            case TieBreakType.AVERAGE_PERFECT_PERFORMANCE:
                return 'APPO'
            case TieBreakType.DIRECT_ENCOUNTER:
                return 'DE'
            case _:
                raise ValueError(f'Unknown tie break: {self}')

    @property
    def options(self) -> list[TieBreakOption]:
        match self:
            case TieBreakType.WINS:
                return []
            case TieBreakType.GAMES_WON:
                return []
            case TieBreakType.GAMES_PLAYED_WITH_BLACK:
                return []
            case TieBreakType.GAMES_WON_WITH_BLACK:
                return []
            case TieBreakType.PROGRESSIVE_SCORES:
                return [TieBreakOption.CUT]
            case TieBreakType.ROUNDS_ELECTED_TO_PLAY:
                return []
            case TieBreakType.BUCHHOLZ:
                return [
                    TieBreakOption.CUT_TOP,
                    TieBreakOption.CUT_BOTTOM,
                    TieBreakOption.PLAYED_MODIFIER,
                    TieBreakOption.PAPI_LEGACY,
                ]
            case TieBreakType.AVERAGE_OF_BUCHHOLZ:
                return [TieBreakOption.FORE_MODIFIER]
            case TieBreakType.FORE_BUCHHOLZ:
                return [
                    TieBreakOption.CUT_TOP,
                    TieBreakOption.CUT_BOTTOM,
                    TieBreakOption.PLAYED_MODIFIER,
                ]
            case TieBreakType.SUM_OF_BUCHHOLZ:
                return [
                    TieBreakOption.FORE_MODIFIER,
                    TieBreakOption.PAPI_LEGACY,
                ]
            case TieBreakType.SONNENBORN_BERGER:
                return [
                    TieBreakOption.CUT,
                    TieBreakOption.PLAYED_MODIFIER,
                ]
            case TieBreakType.KOYA:
                return [TieBreakOption.LIMIT]
            case TieBreakType.AVERAGE_RATING_OPPONENTS:
                return [
                    TieBreakOption.CUT_TOP,
                    TieBreakOption.CUT_BOTTOM,
                ]
            case TieBreakType.TOURNAMENT_PERFORMANCE_RATING:
                return [TieBreakOption.PAPI_LEGACY]
            case TieBreakType.AVERAGE_PERFORMANCE_RATING_OPPONENTS:
                return []
            case TieBreakType.PERFECT_TOURNAMENT_PERFORMANCE:
                return []
            case TieBreakType.AVERAGE_PERFECT_PERFORMANCE:
                return []
            case TieBreakType.DIRECT_ENCOUNTER:
                return [
                    TieBreakOption.EXCLUDE_IDS,
                    TieBreakOption.PLAYED_MODIFIER,
                ]
            case _:
                raise ValueError(f'Unknown tie break: {self}')


@dataclass
class TieBreak:
    type: TieBreakType
    options: dict[TieBreakOption, Any]

    def player_value(
        self,
        player: 'Player',
        tournament: 'Tournament',
        max_round: int | None = None,
    ) -> int | float:
        self._check_options()
        return self.type.compute_function(
            player,
            tournament,
            max_round=max_round,
            **self.options,
        )

    def _check_options(self):
        for option, value in self.options.items():
            if option not in self.type.options:
                raise ValueError(
                    f'Option "{option.value}" is not allowed '
                    f'for tie break "{self.type.value}"'
                )
            if not isinstance(value, option.type):
                raise ValueError(
                    f'Unexpected value for option "{option.value}": '
                    f'"{value}" (expected_type: {option.type})'
                )
