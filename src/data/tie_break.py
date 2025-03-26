import itertools
from abc import ABC, abstractmethod
from bisect import bisect_right
from collections import namedtuple
from collections.abc import Iterable
from contextlib import suppress
from decimal import Decimal
from functools import partial
from math import isclose
from types import UnionType
from typing import Any, TYPE_CHECKING, override

from common.i18n import _
from data.pairing import Pairing
from data.util import (
    Result,
    BoardColor,
    TournamentPairing,
    StaticUtils,
    AbstractOption,
    AbstractOptionHandler,
    OptionError,
)
from plugins.manager import plugin_manager

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparisonT
    from data.player import Player
    from data.tournament import Tournament


TIE_BREAK_CLASSES: list[type['AbstractTieBreak']] = []
OPTION_CLASSES: list[type['AbstractTieBreakOption']] = []


register_tie_break = partial(
    StaticUtils.register_class, register=TIE_BREAK_CLASSES
)
register_option = partial(StaticUtils.register_class, register=OPTION_CLASSES)


class TieBreakManager:
    """Entry class for interacting with tie-breaks"""

    @staticmethod
    def tie_break_types() -> list[type['AbstractTieBreak']]:
        return TIE_BREAK_CLASSES + list(itertools.chain.from_iterable(
            plugin_manager.hook.get_extra_tie_break_classes()
        ))

    @classmethod
    def tie_break_type_by_id(cls) -> dict[str, type['AbstractTieBreak']]:
        return {
            tie_break_type.identifier(): tie_break_type
            for tie_break_type in cls.tie_break_types()
        }

    @classmethod
    def tie_break_by_papi_id(cls) -> dict[str, 'AbstractTieBreak']:
        papi_tie_breaks: dict[str, 'AbstractTieBreak'] = {}
        for tie_break_type in cls.tie_break_types():
            tie_break = tie_break_type()
            if tie_break.papi_id:
                papi_tie_breaks[tie_break.papi_id] = tie_break
        return papi_tie_breaks

    @classmethod
    def papi_compatible_tie_breaks(cls) -> list['AbstractTieBreak']:
        """List of tie-breaks that can be used in papi"""
        return [
            tie_break_type() for tie_break_type in cls.tie_break_types()
            if tie_break_type().papi_id is not None
        ]

    @staticmethod
    def option_types() -> list[type['AbstractTieBreakOption']]:
        return OPTION_CLASSES

    @classmethod
    def option_type_by_id(cls) -> dict[str, type['AbstractTieBreakOption']]:
        return {
            option_type.identifier(): option_type
            for option_type in cls.option_types()
        }


class AbstractTieBreakOption(AbstractOption, ABC):
    """Abstract class representing an option of a tie-break"""
    @property
    def template_name(self) -> str:
        # TODO Implement templates for tie-break options
        return ''


class AbstractTieBreak(AbstractOptionHandler, ABC):
    """Abstract class representing a tie-break"""

    @property
    @abstractmethod
    def acronym(self) -> str:
        pass

    @property
    @abstractmethod
    def short_name(self) -> str:
        pass

    @abstractmethod
    def compute_player_value(
        self,
        player: 'Player',
        *,
        after_round: int | None,
    ) -> 'SupportsRichComparisonT':
        """Compute the value of the tie-break for a player.
        As tie-breaks are intended for ranking, 
        the return type need to support rich comparison with himself"""
        pass

    @property
    def is_displayable(self) -> bool:
        """Defines if the tie-break can be displayed
        in a print view or a ranking screen"""
        return True

    @property
    def papi_id(self) -> str | None:
        """Represents the tie-break in a Papi database.
        If None, the tie-break will not appear in the database"""
        return None

    def to_dict(self) -> dict:
        return {
            'type': self.id,
            'options': {
                option.id: option.value for option in self.options
            }
        }


class TieBreakUtils:
    """Utilities for tie-breaks"""

    @staticmethod
    def adjusted_score(
        player: 'Player',
        *,
        after_round: int,
        adjust_fore: bool = False,
    ) -> float:
        """Computes the adjusted score of the player for the purposes of their opponents' tie-breaks
        Only adjusts them in case of requested byes followed by all VUR.
        If *adjust_fore* is True, the adjusted score for Fore Buchholz is computed:
        games for the last round not determined over the board are considered as draws."""
        tournament: 'Tournament' = player.tournament
        if tournament.pairing == TournamentPairing.BERGER:
            return player.points_after(after_round)
        score = 0
        for round_index, pairing in player.pairings.items():
            if round_index > after_round:
                continue
            if adjust_fore and round_index == after_round:
                if pairing.result in (
                    Result.FULL_POINT_BYE,
                    Result.PAIRING_ALLOCATED_BYE,
                ):
                    score += pairing.result.points(tournament.point_values)
                else:
                    score += Result.DRAW.points(tournament.point_values)
                continue
            if pairing.requested_bye:
                if all(
                    p.voluntary_unplayed
                    for index, p in player.pairings.items()
                    if round_index < index <= after_round
                ):
                    score += Result.DRAW.points(tournament.point_values)
                else:
                    score += pairing.result.points(tournament.point_values)
            else:
                score += pairing.result.points(tournament.point_values)
        return score

    @staticmethod
    def buchholz_dummy_score(
        player: 'Player',
        *,
        after_round: int = 1,
        fore_modifier: bool = False,
    ) -> float | tuple[float, Result]:
        """Computes the dummy score for the given pairing after *after_round*."""
        if not fore_modifier:
            return player.points_after(after_round)
        dummy = player.points_before(after_round)
        last_pairing = player.pairings[after_round]
        if last_pairing.result in (
            Result.FULL_POINT_BYE, Result.PAIRING_ALLOCATED_BYE,
            Result.HALF_POINT_BYE, Result.ZERO_POINT_BYE
        ):
            dummy += last_pairing.result.points(player.point_values)
        else:
            dummy += Result.DRAW.points(player.point_values)
        return dummy


class AbstractCutTieBreakOption(AbstractTieBreakOption, ABC):
    @property
    def type(self) -> type | UnionType:
        return int

    @property
    def default_value(self) -> Any:
        return 0

    @override
    def validate(self):
        super().validate()
        if self.value < 0:
            raise OptionError(_('A positive integer is expected.'), self)


@register_option
class CutTieBreakOption(AbstractCutTieBreakOption):
    @staticmethod
    def identifier() -> str:
        return 'CUT'


@register_option
class CutTopTieBreakOption(AbstractCutTieBreakOption):
    @staticmethod
    def identifier() -> str:
        return 'CUT_TOP'


@register_option
class CutBottomTieBreakOption(AbstractCutTieBreakOption):
    @staticmethod
    def identifier() -> str:
        return 'CUT_BOTTOM'


@register_option
class PlayedModifierTieBreakOption(AbstractTieBreakOption):
    @staticmethod
    def identifier() -> str:
        return 'PLAYED_MODIFIER'

    @property
    def type(self) -> type | UnionType:
        return bool

    @property
    def default_value(self) -> Any:
        return False


@register_option
class ForeModifierTieBreakOption(AbstractTieBreakOption):
    @staticmethod
    def identifier() -> str:
        return 'FORE_MODIFIER'

    @property
    def type(self) -> type | UnionType:
        return bool

    @property
    def default_value(self) -> Any:
        return False


@register_option
class LimitTieBreakOption(AbstractTieBreakOption):
    @staticmethod
    def identifier() -> str:
        return 'LIMIT'

    @property
    def type(self) -> type | UnionType:
        return float | None

    @property
    def default_value(self) -> Any:
        return None


@register_option
class ExcludeIdsTieBreakOption(AbstractTieBreakOption):
    @staticmethod
    def identifier() -> str:
        return 'EXCLUDE_IDS'

    @property
    def type(self) -> type | UnionType:
        return Iterable[int] | None

    @property
    def default_value(self) -> Any:
        return None


@register_tie_break
class WinsTieBreak(AbstractTieBreak):
    """The number of rounds where a participant obtains,
    with or without playing, as many points as awarded for a win.
    See FIDE Handbook C.07.7.1"""

    @property
    def name(self) -> str:
        return _('Number of wins')

    @staticmethod
    def identifier() -> str:
        return 'WINS'

    @property
    def papi_id(self) -> str:
        return 'Nombre de Victoires'

    @property
    def acronym(self) -> str:
        # FIDE acronym: 'WIN'
        return _('NW *** ACRONYM FOR PAPI NUMBER OF WINS')

    @property
    def short_name(self) -> str:
        return _('Wins')

    def compute_player_value(
        self,
        player: 'Player',
        *,
        after_round: int | None,
    ) -> int:
        if after_round is None:
            after_round = max(player.pairings)
        point_values = player.tournament.point_values
        return sum(
            pairing.result.points(point_values) == Result.GAIN.points(
                point_values
            ) for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        )


@register_tie_break
class GamesWonTieBreak(AbstractTieBreak):
    """The number of games a participant won 'over the board'.
    See FIDE Handbook C.07.7.2"""

    @property
    def name(self) -> str:
        return _('Number of games won')

    @staticmethod
    def identifier() -> str:
        return 'GAMES_WON'

    @property
    def acronym(self) -> str:
        return 'WON'

    @property
    def short_name(self) -> str:
        return _('Games won')

    def compute_player_value(
        self,
        player: 'Player',
        *,
        after_round: int | None,
    ) -> int:
        if after_round is None:
            after_round = max(player.pairings)
        return sum(
            pairing.result == Result.GAIN
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        )


@register_tie_break
class GamesPlayedWithBlackTieBreak(AbstractTieBreak):
    """The number of games played over the board with the black pieces.
    See FIDE Handbook C.07.7.3"""

    @property
    def name(self) -> str:
        return _('Games played with black')

    @staticmethod
    def identifier() -> str:
        return 'GAMES_PLAYED_WITH_BLACK'

    @property
    def acronym(self) -> str:
        return 'BPG'

    @property
    def short_name(self) -> str:
        return _('Black games')

    def compute_player_value(
        self,
        player: 'Player',
        *,
        after_round: int | None,
    ) -> int:
        if after_round is None:
            after_round = max(player.pairings)
        return sum(
            pairing.color == BoardColor.BLACK and pairing.played
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        )


@register_tie_break
class GamesWonWithBlackTieBreak(AbstractTieBreak):
    """The number of games won over the board with the black pieces.
    See FIDE Handbook C.07.7.4"""

    @property
    def name(self) -> str:
        return _('Games won with black')

    @staticmethod
    def identifier() -> str:
        return 'GAMES_WON_WITH_BLACK'

    @property
    def acronym(self) -> str:
        return 'BWG'

    @property
    def short_name(self) -> str:
        return _('Black wins')

    def compute_player_value(
            self,
            player: 'Player',
            *,
            after_round: int | None,
    ) -> int:
        if after_round is None:
            after_round = max(player.pairings)
        return sum(
            pairing.color == BoardColor.BLACK and pairing.result == Result.GAIN
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        )


@register_tie_break
class ProgressiveScoresTieBreak(AbstractTieBreak):
    """The sum of progressive scores.
    After each round, a participant has a certain tournament score.
    This tie-break is calculated adding the score of the participant at the end of each round.
    Options:
      - CUT: exclude the score achieved after the first *CUT* rounds
    See FIDE Handbook C.07.7.5 and C.07.14.1"""

    @property
    def name(self) -> str:
        return _('Progressive scores')

    @staticmethod
    def identifier() -> str:
        return 'PROGRESSIVE_SCORES'

    @property
    def papi_id(self) -> str:
        return 'Cumulatif'

    @property
    def acronym(self) -> str:
        # FIDE Acronym: 'PS'
        return _('PS *** ACRONYM FOR PAPI PROGRESSIVE SCORE')

    @property
    def short_name(self) -> str:
        return _('Progressive')

    @staticmethod
    def available_options() -> list[type[AbstractTieBreakOption]]:
        return [CutTieBreakOption]

    def compute_player_value(
            self,
            player: 'Player',
            *,
            after_round: int | None,
    ) -> float:
        cut, = self.get_option_values()
        if after_round is None:
            after_round = max(player.pairings)
        return sum(player.points_after(r) for r in range(1 + cut, after_round + 1))


@register_tie_break
class RoundsElectedToPlayTieBreak(AbstractTieBreak):
    """The number of rounds one elected to play, i.e. the rounds where a player
    did not lose by forfeit, nor elected to take a bye (ZPB, HPB, or FPB)
    See FIDE Handbook C.07.7.6"""

    @property
    def name(self) -> str:
        return _('Rounds one Elected to Play')

    @staticmethod
    def identifier() -> str:
        return 'ROUNDS_ELECTED_TO_PLAY'

    @property
    def acronym(self) -> str:
        return 'REP'

    @property
    def short_name(self) -> str:
        return _('Games played')

    def compute_player_value(
            self,
            player: 'Player',
            *,
            after_round: int | None,
    ) -> int:
        if after_round is None:
            after_round = max(player.pairings)
        return sum(
            pairing.result
            not in (
                Result.FORFEIT_LOSS,
                Result.DOUBLE_FORFEIT,
                Result.ZERO_POINT_BYE,
                Result.HALF_POINT_BYE,
                Result.FULL_POINT_BYE,
            )
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        )


@register_tie_break
class BuchholzTieBreak(AbstractTieBreak):
    """The sum of the scores of each of the opponents of a participant.
    Options:
      - CUT_TOP: removes the *cut_top* highest contributions.
      - CUT_BOTTOM: removes the *cut_bottom* the lowest contributions.
    When cutting the lowest contributions, all Voluntary Unplayed Rounds
    (requested byes and forfeit losses) are cut before any other round is cut.
    Both values must be non-negative.
    *cut_top* must be at most equal to *cut_bottom*.
      - PLAYED_MODIFIER: When True, forfeit losses and wins are considered
    played against the scheduled opponent.
    See FIDE Handbook C.07.8.1"""

    @property
    def name(self) -> str:
        return _('Buchholz')

    @staticmethod
    def identifier() -> str:
        return 'BUCHHOLZ'

    @property
    def acronym(self) -> str:
        return 'BH'


    @property
    def short_name(self) -> str:
        return _('Buchholz')

    @staticmethod
    def available_options() -> list[type[AbstractTieBreakOption]]:
        return [
            CutTopTieBreakOption,
            CutBottomTieBreakOption,
            PlayedModifierTieBreakOption,
        ]

    def validate_options(self):
        super().validate_options()
        cut_top, cut_bottom, _played = self.get_option_values()
        if cut_top and cut_top < cut_bottom:
            raise OptionError(
                _(f'Top cut must be at most equal to bottom cut.'),
                self._get_option(CutTopTieBreakOption)
            )

    def compute_player_value(
        self,
        player: 'Player',
        *,
        after_round: int | None,
    ) -> float:
        cut_top, cut_btm, played_modifier = self.get_option_values()
        if after_round is None:
            after_round = max(player.pairings)
        elif cut_top + cut_btm >= after_round:
            return 0
        tournament: 'Tournament' = player.tournament
        pairings: dict[int, Pairing] = {
            round_index: pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        }
        if tournament.pairing == TournamentPairing.BERGER:
            return sum(
                TieBreakUtils.adjusted_score(
                    tournament.players_by_id[pairing.opponent_id],
                    after_round=after_round,
                )
                for pairing in pairings.values()
                if pairing.opponent_id is not None
            )
        scores: list[float] = []
        voluntary_unplayed: list[float] = []
        for round_index, pairing in pairings.items():
            should_add_dummy = tournament.pairing.swiss and (
                (pairing.unplayed and not played_modifier) or
                (played_modifier and pairing.result in (
                    Result.HALF_POINT_BYE, Result.ZERO_POINT_BYE,
                    Result.FULL_POINT_BYE, Result.PAIRING_ALLOCATED_BYE
                ))
            )
            if should_add_dummy:
                dummy_points = TieBreakUtils.buchholz_dummy_score(player, after_round=after_round)
                if pairing.voluntary_unplayed:
                    # We must take those into account to ensure
                    # correct computations for cut-1
                    voluntary_unplayed.append(dummy_points)
                else:
                    scores.append(dummy_points)
                continue
            opponent: Player = tournament.players_by_id[pairing.opponent_id]
            if tournament.pairing.swiss:
                opponent_adjusted_score = TieBreakUtils.adjusted_score(
                    opponent, after_round=after_round
                )
            else:
                opponent_adjusted_score = opponent.points_after(after_round)
            scores.append(opponent_adjusted_score)
        voluntary_unplayed = sorted(voluntary_unplayed)
        scores = sorted(scores)
        scores = voluntary_unplayed + scores

        if cut_top:
            return sum(scores[cut_btm:-cut_top])
        return sum(scores[cut_btm:])


@register_tie_break
class ForeBuchholzTieBreak(AbstractTieBreak):
    """the Buchholz score as if all paired games for the final round had ended in draws.
    Options:
      - CUT_TOP: removes the *cut_top* highest contributions.
      - CUT_BOTTOM: removes the *cut_bottom* the lowest contributions.
    When cutting the lowest contributions, all Voluntary Unplayed Rounds
    (requested byes and forfeit losses) are cut before any other round is cut.
    Both values must be non-negative.
    *cut_top* must be at most equal to *cut_bottom*.
      - PLAYED_MODIFIER: When True, forfeit losses and wins are considered
    played against the scheduled opponent.
    See FIDE Handbook C.07.8.3"""

    @property
    def name(self) -> str:
        return _('Fore Buchholz')

    @staticmethod
    def identifier() -> str:
        return 'FORE_BUCHHOLZ'

    @property
    def acronym(self) -> str:
        return 'FB'

    @property
    def short_name(self) -> str:
        return _('Fore Bu. *** SHORT NAME FOR FORE BUCHHOLZ')

    @staticmethod
    def available_options() -> list[type[AbstractTieBreakOption]]:
        return [
            CutTopTieBreakOption,
            CutBottomTieBreakOption,
            PlayedModifierTieBreakOption,
        ]

    def validate_options(self):
        super().validate_options()
        cut_top, cut_bottom, _played = self.get_option_values()
        if cut_top and cut_top < cut_bottom:
            raise OptionError(
                _(f'Top cut must be at most equal to bottom cut.'),
                self._get_option(CutTopTieBreakOption)
            )

    def compute_player_value(
        self,
        player: 'Player',
        *,
        after_round: int | None,
    ) -> float:
        cut_top, cut_btm, played_modifier = self.get_option_values()
        if after_round is None:
            after_round = max(player.pairings)
        elif cut_top + cut_btm >= after_round:
            return 0
        pairings: dict[int, Pairing] = {
            round_index: pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        }
        scores: list[float] = []
        voluntary_unplayed: list[float] = []
        dummy_points = TieBreakUtils.buchholz_dummy_score(
            player, after_round=after_round, fore_modifier=True
        )
        tournament: 'Tournament' = player.tournament
        for pairing in pairings.values():
            should_add_dummy = (
                (pairing.unplayed and not played_modifier) or
                (played_modifier and pairing.result in (
                    Result.HALF_POINT_BYE, Result.ZERO_POINT_BYE,
                    Result.FULL_POINT_BYE, Result.PAIRING_ALLOCATED_BYE
                ))
            )
            if should_add_dummy:
                if pairing.voluntary_unplayed:
                    # We must take those into account to ensure
                    # correct computations for cut-1
                    voluntary_unplayed.append(dummy_points)
                else:
                    scores.append(dummy_points)
                continue
            opponent: Player = tournament.players_by_id[pairing.opponent_id]
            opponent_adjusted_score = TieBreakUtils.adjusted_score(
                opponent, after_round=after_round, adjust_fore=True
            )
            scores.append(opponent_adjusted_score)
        voluntary_unplayed = sorted(voluntary_unplayed)
        scores = sorted(scores)
        scores = voluntary_unplayed + scores

        if cut_top:
            return sum(scores[cut_btm:-cut_top])
        return sum(scores[cut_btm:])


@register_tie_break
class SumOfBuchholzTieBreak(AbstractTieBreak):
    """The sum of Buchholz scores of the opponents.
    Options:
      - FORE_MODIFIER: When True, will use Fore Bochholz instead of total Buchholz.
    """

    @property
    def name(self) -> str:
        return _('Sum of Buchholz')

    @staticmethod
    def identifier() -> str:
        return 'SUM_OF_BUCHHOLZ'

    @property
    def acronym(self) -> str:
        return 'SOB'

    @property
    def short_name(self) -> str:
        return _('Bu. sum *** SHORT NAME FOR SUM OF BUCHHOLZ')

    @staticmethod
    def available_options() -> list[type[AbstractTieBreakOption]]:
        return [ForeModifierTieBreakOption]

    def compute_player_value(
        self,
        player: 'Player',
        *,
        after_round: int | None,
    ) -> float:
        tournament: 'Tournament' = player.tournament
        fore_modifier, = self.get_option_values()
        if after_round is None:
            after_round = max(player.pairings)
        opponents: list[Player | None] = [
            tournament.players_by_id.get(pairing.opponent_id)
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        ]
        tie_break = (
            ForeBuchholzTieBreak() if fore_modifier else BuchholzTieBreak()
        )
        return sum(
            tie_break.compute_player_value(opponent, after_round=after_round)
            for opponent in opponents if opponent is not None
        )


@register_tie_break
class AverageOfBuchholzTieBreak(AbstractTieBreak):
    """The average of opponents Buchholz scores.
    Options:
      - FORE_MODIFIER: When True, will use Fore Bochholz instead of total Buchholz.
    See FIDE Handbook C.07.8.2."""

    @property
    def name(self) -> str:
        return _('Average of opponents Buchholz')

    @staticmethod
    def identifier() -> str:
        return 'AVERAGE_OF_BUCHHOLZ'

    @property
    def acronym(self) -> str:
        return 'AOB'

    @property
    def short_name(self) -> str:
        return _('Average Bu. *** SHORT NAME FOR AVERAGE OF BUCHHOLZ')

    @staticmethod
    def available_options() -> list[type[AbstractTieBreakOption]]:
        return [ForeModifierTieBreakOption]

    def compute_player_value(
        self,
        player: 'Player',
        *,
        after_round: int | None,
    ) -> float:
        tournament: 'Tournament' = player.tournament
        fore_modifier, = self.get_option_values()
        if after_round is None:
            after_round = max(player.pairings)
        opponents: list[Player] = [
            tournament.players_by_id[pairing.opponent_id]
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round and pairing.opponent_id is not None
            and pairing.played
        ]
        tie_break = (
            ForeBuchholzTieBreak() if fore_modifier else BuchholzTieBreak()
        )
        return sum(
            tie_break.compute_player_value(opponent, after_round=after_round)
            for opponent in opponents if opponent is not None
        ) / len(opponents)


@register_tie_break
class SonnebornBergerTieBreak(AbstractTieBreak):
    """Score computed by adding, for each round,
    a value given by multiplying their score of the opponent by
    the points scored against them.
    Options:
      - CUT: If *cut* is more than zero, will cut the *cut* lowest contributions.
      - PLAYED_MODIFIER: When True, forfeit wins and losses will be counted
    as played games (only relevant in Swiss tournaments).
    See FIDE Handbook C.07.9.1."""

    @property
    def name(self) -> str:
        return _('Sonnenborn-Berger')

    @staticmethod
    def identifier() -> str:
        return 'SONNENBORN_BERGER'

    @property
    def papi_id(self) -> str:
        return 'Sonnenborn-Berger'

    @property
    def acronym(self) -> str:
        return 'SB'

    @property
    def short_name(self) -> str:
        return _('S-Berger *** SHORT NAME FOR SONNENBORN-BERGER')

    @staticmethod
    def available_options() -> list[type[AbstractTieBreakOption]]:
        return [
            CutTieBreakOption,
            PlayedModifierTieBreakOption,
        ]

    def compute_player_value(
        self,
        player: 'Player',
        *,
        after_round: int | None,
    ) -> float:
        tournament: 'Tournament' = player.tournament
        cut, played_modifier = self.get_option_values()
        if after_round is None:
            after_round = max(player.pairings)
        if cut >= after_round:
            return 0
        if tournament.pairing == TournamentPairing.BERGER:
            played_modifier = True
        pairings: dict[int, Pairing] = {
            round_index: pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        }
        SBContribution = namedtuple('SBContribution', ['score', 'contribution'])
        general_contributions: list[SBContribution] = []
        voluntary_unplayed: list[SBContribution] = []
        for round_index, pairing in pairings.items():
            if pairing.unplayed and not played_modifier:
                dummy, result = self._dummy_score(player, pairing, after_round=after_round)
                value = dummy * result.points(tournament.point_values)
                if not pairing.voluntary_unplayed:
                    general_contributions.append(SBContribution(dummy, value))
                else:
                    voluntary_unplayed.append(SBContribution(dummy, value))
            elif pairing.played or (
                    pairing.unplayed and pairing.opponent_id is not None and played_modifier
            ):
                opponent: Player = tournament.players_by_id[pairing.opponent_id]
                opponent_score = TieBreakUtils.adjusted_score(
                    opponent, after_round=after_round
                )
                contribution = pairing.result.points(tournament.point_values) * opponent_score
                general_contributions.append(SBContribution(opponent_score, contribution))
        voluntary_unplayed = sorted(voluntary_unplayed)
        general_contributions = sorted(general_contributions)
        for _ in range(cut):
            if not voluntary_unplayed:
                # Suppress, because both lists are empty at this point
                with suppress(IndexError):
                    general_contributions.pop(0)
            elif not general_contributions:
                with suppress(IndexError):
                    # Suppress, because both lists are empty
                    voluntary_unplayed.pop(0)
            else:
                # At this point, we know both lists have at least an element
                vur = voluntary_unplayed[0]
                lsv = general_contributions[0]
                if vur.score <= lsv.score:
                    voluntary_unplayed.pop(0)
                # Cut the lowest contribution from a VUR only if it is not lower
                # than the least significant value
                elif vur.contribution >= lsv.contribution:
                    voluntary_unplayed.pop(0)
                else:
                    general_contributions.pop(0)

        return sum(
            map(
                lambda t: t.contribution,
                voluntary_unplayed + general_contributions
            )
        )

    @staticmethod
    def _dummy_score(
        player: 'Player',
        pairing: Pairing,
        *,
        after_round: int = 1,
    ) -> tuple[float, Result]:
        """Computes the dummy score for the given pairing after *after_round*."""
        dummy = player.points_after(after_round)
        match pairing.result:
            case Result.FORFEIT_GAIN | Result.PAIRING_ALLOCATED_BYE | Result.FULL_POINT_BYE:
                return dummy, Result.GAIN
            case Result.HALF_POINT_BYE:
                return dummy, Result.DRAW
            case Result.ZERO_POINT_BYE | Result.FORFEIT_LOSS | Result.DOUBLE_FORFEIT | Result.NO_RESULT:
                return dummy, Result.LOSS
            case _:
                return dummy, pairing.result


@register_tie_break
class KoyaTieBreak(AbstractTieBreak):
    """The number of points achieved against all participants
    who have scored at 50% of the maximum possible score.
    This is only used in Round-Robin tournaments, but is still
    defined for Swiss tournaments.
    Options:
      - LIMIT: if set, this function will compute the points obtained
    against opponents who have at least *limit* points.
    See FIDE Handbook C.07.9.2."""

    @property
    def name(self) -> str:
        return _('Koya system')

    @staticmethod
    def identifier() -> str:
        return 'KOYA'

    @property
    def papi_id(self) -> str:
        return 'Koya'

    @property
    def acronym(self) -> str:
        # FIDE Acronym: 'KS'
        return _('Ko. *** ACRONYM FOR PAPI KOYA')

    @property
    def short_name(self) -> str:
        return _('Koya')

    @staticmethod
    def available_options() -> list[type[AbstractTieBreakOption]]:
        return [LimitTieBreakOption]

    def compute_player_value(
        self,
        player: 'Player',
        *,
        after_round: int | None,
    ) -> float:
        tournament: 'Tournament' = player.tournament
        limit, = self.get_option_values()
        if after_round is None:
            after_round = max(player.pairings)
        if limit is None:
            limit = 0.5 * Result.GAIN.points(tournament.point_values) * (after_round - 1)
        pairings: dict[int, Pairing] = {
            round_index: pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        }
        score = 0
        for _round_index, pairing in pairings.items():
            if pairing.opponent_id is None:
                continue
            opponent = tournament.players_by_id[pairing.opponent_id]
            opponent_score = opponent.points_before(after_round)
            if opponent_score >= limit:
                score += pairing.result.points(tournament.point_values)
        return score


@register_tie_break
class KashdanTieBreak(AbstractTieBreak):
    """Grant 4 tiebreak points for a win, 2 for a draw, 1 for a loss,
    and 0 for an unplayed game.
    See USCF Handbook section 34E7."""

    @property
    def name(self) -> str:
        return _('Kashdan')

    @staticmethod
    def identifier() -> str:
        return 'KASHDAN'

    @property
    def acronym(self) -> str:
        return 'KA'

    @property
    def short_name(self) -> str:
        return _('Kashdan')

    def compute_player_value(
        self,
        player: 'Player',
        *,
        after_round: int | None,
    ) -> int:
        if after_round is None:
            after_round = max(player.pairings)

        pairings: list[Pairing] = [
            pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        ]
        score_by_result: dict[Result, int] = {
            Result.GAIN: 4,
            Result.UNRATED_GAIN: 4,
            Result.DRAW: 2,
            Result.UNRATED_DRAW: 2,
            Result.LOSS: 1,
            Result.UNRATED_LOSS: 1,
            Result.FORFEIT_GAIN: 0,
            Result.PAIRING_ALLOCATED_BYE: 0,
            Result.FULL_POINT_BYE: 0,
            Result.HALF_POINT_BYE: 0,
            Result.NO_RESULT: 0,
            Result.ZERO_POINT_BYE: 0,
            Result.FORFEIT_LOSS: 0,
            Result.DOUBLE_FORFEIT: 0,
        }
        return sum(pairing.result.points(score_by_result) for pairing in pairings)


@register_tie_break
class AverageRatingOpponentsTieBreak(AbstractTieBreak):
    """The average rating of opponents.
    Only opponents met over the board will be counted.
    WARNING: This assumes everyone has a rating; if an opponent does not have
    a rating, they will be removed from consideration.
    Options:
      - CUT_TOP: remove the highest *cut_top* ratings.
      - CUT_BOTTOM: remove the lowest *cut_bottom* ratings.
    See FIDE Handbook C.07.10.1"""

    @property
    def name(self) -> str:
        return _('Average rating of opponents')

    @staticmethod
    def identifier() -> str:
        return 'AVERAGE_RATING_OPPONENTS'

    @property
    def acronym(self) -> str:
        return 'ARO'

    @property
    def short_name(self) -> str:
        return _('Average rating')

    @staticmethod
    def available_options() -> list[type[AbstractTieBreakOption]]:
        return [
            CutTopTieBreakOption,
            CutBottomTieBreakOption,
        ]

    def validate_options(self):
        super().validate_options()
        cut_top, cut_bottom = self.get_option_values()
        if cut_top and cut_top < cut_bottom:
            raise OptionError(
                _(f'Top cut must be at most equal to bottom cut.'),
                self._get_option(CutTopTieBreakOption)
            )

    def compute_player_value(
        self,
        player: 'Player',
        *,
        after_round: int | None,
    ) -> int:
        tournament: 'Tournament' = player.tournament
        cut_top, cut_btm = self.get_option_values()
        if after_round is None:
            after_round = max(player.pairings)
        if cut_top + cut_btm >= after_round:
            return 0
        pairings: list[Pairing] = [
            pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        ]
        ratings = []
        for pairing in pairings:
            if pairing.unplayed:
                continue
            opponent = tournament.players_by_id[pairing.opponent_id]
            with suppress(KeyError):
                ratings.append(opponent.estimation)
        ratings = sorted(ratings)
        if cut_top:
            ratings = ratings[cut_btm:-cut_top]
        else:
            ratings = ratings[cut_btm:]
        if not ratings:
            return 0
        average = sum(ratings) / len(ratings)
        return StaticUtils.round_ranking(average)


@register_tie_break
class TournamentPerformanceRatingTieBreak(AbstractTieBreak):
    """The Average Rating of the Opponents, added
    to a number resulting from the conversion of the fractional score
    into RD (see FIDE Rating Regulations for the Conversion Table).
    See FIDE Handbook C.07.10.2."""

    @property
    def name(self) -> str:
        return _('Tournament performance rating')

    @staticmethod
    def identifier() -> str:
        return 'TOURNAMENT_PERFORMANCE_RATING'

    @property
    def acronym(self) -> str:
        return 'TPR'

    @property
    def short_name(self) -> str:
        return _('Performance')

    def compute_player_value(
            self,
            player: 'Player',
            *,
            after_round: int | None,
    ) -> int:
        tournament: 'Tournament' = player.tournament
        if after_round is None:
            after_round = max(player.pairings)
        pairings: list[Pairing] = [
            pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round and pairing.played
        ]
        ratings = []
        score = 0
        for pairing in pairings:
            opponent = tournament.players_by_id[pairing.opponent_id]
            with suppress(KeyError):
                rating = opponent.estimation
                ratings.append(rating)
                score += pairing.result.points(tournament.point_values)
        if not ratings:
            return 0
        max_score = len(ratings) * Result.GAIN.points(tournament.point_values)
        average = sum(ratings) / len(ratings)
        fractional_score = round(score / max_score, 2)
        bonus = StaticUtils.performance_bonus(fractional_score)
        return StaticUtils.round_ranking(average + bonus)


@register_tie_break
class AveragePerformanceRatingOpponentsTieBreak(AbstractTieBreak):
    """The average of the tournament performance rating of the
    opponents, only taking played games into account.
    See FIDE Handbook C.07.10.4."""

    @property
    def name(self) -> str:
        return _('Average performance rating of opponents')

    @staticmethod
    def identifier() -> str:
        return 'AVERAGE_PERFORMANCE_RATING_OPPONENTS'

    @property
    def acronym(self) -> str:
        return 'APRO'

    @property
    def short_name(self) -> str:
        return _(
            'Average perf. *** SHORT NAME FOR AVERAGE'
            ' PERFORMANCE RATING OPPONENTS'
        )

    def compute_player_value(
            self,
            player: 'Player',
            *,
            after_round: int | None,
    ) -> int:
        tournament: 'Tournament' = player.tournament
        if after_round is None:
            after_round = max(player.pairings)
        played_games: list[Pairing] = [
            pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round and pairing.played
        ]
        performance_ratings = []
        performance_tie_break = TournamentPerformanceRatingTieBreak()
        for pairing in played_games:
            opponent: Player = tournament.players_by_id[pairing.opponent_id]
            opponent_tpr = performance_tie_break.compute_player_value(
                opponent, after_round=after_round
            )
            performance_ratings.append(opponent_tpr)

        average = sum(performance_ratings) / len(performance_ratings)
        return StaticUtils.round_ranking(average)


@register_tie_break
class PerfectTournamentPerformanceTieBreak(AbstractTieBreak):
    """The lowest rating that a participant should have for their
    expected score to be greater than or equal to their tournament score.
    This assumes that all players are rated, or at least have an estimation.
    See FIDE Handbook C.07.10.3."""

    @property
    def name(self) -> str:
        return _('Perfect tournament performance')

    @staticmethod
    def identifier() -> str:
        return 'PERFECT_TOURNAMENT_PERFORMANCE'

    @property
    def acronym(self) -> str:
        return 'PTP'

    @property
    def short_name(self) -> str:
        return _(
            'Perfect perf. *** SHORT NAME '
            'FOR PERFECT TOURNAMENT PERFORMANCE'
        )

    def compute_player_value(
            self,
            player: 'Player',
            *,
            after_round: int | None,
    ) -> int:
        if after_round is None:
            after_round = max(player.pairings)
        played_rounds: list[Pairing] = [
            pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round and pairing.played
        ]
        if not played_rounds:
            return 0
        tournament: 'Tournament' = player.tournament
        actual_score = Decimal(
            sum(
                pairing.result.points(tournament.point_values)
                for pairing in played_rounds
            )
        )
        if actual_score == len(played_rounds) * Result.LOSS.points(tournament.point_values):
            return -800 + min(
                tournament.players_by_id[pairing.opponent_id].estimation
                for pairing in played_rounds
            )
        ratings: list[int] = [
            tournament.players_by_id[pairing.opponent_id].estimation
            for pairing in played_rounds
        ]
        performance_tie_break = TournamentPerformanceRatingTieBreak()
        first_estimation = performance_tie_break.compute_player_value(
            player, after_round=after_round
        )
        first_expected_score = self._expected_score(
            first_estimation, ratings, tournament.point_values
        )
        if isclose(first_expected_score, actual_score, abs_tol=0.01):
            return StaticUtils.round_ranking(first_estimation)
        second_estimation = first_estimation * actual_score / first_expected_score
        second_estimation = StaticUtils.round_ranking(float(second_estimation))
        second_expected_score = self._expected_score(
            second_estimation, ratings, tournament.point_values
        )

        if first_expected_score >= second_expected_score:
            low, high = second_estimation, first_estimation
        else:
            low, high = first_estimation, second_estimation
        while not isclose(
                actual_score,
                mid_score := self._expected_score(
                    (mid := (low + high) / 2), ratings, tournament.point_values
                ),
                abs_tol=0.01
        ):
            if mid_score >= actual_score:
                high = mid
            else:
                low = mid
        mid = StaticUtils.round_ranking(mid)
        while self._expected_score(
            mid, ratings, tournament.point_values
        ) >= actual_score:
            mid -= 1
        while self._expected_score(
            mid, ratings, tournament.point_values
        ) < actual_score:
            mid += 1
        return StaticUtils.round_ranking(mid)

    @classmethod
    def _expected_score(
        cls,
        player_rating: int,
        opponent_ratings: Iterable[int],
        point_values: dict[Result, float] | None = None,
    ) -> Decimal:
        chances = [
            cls.win_chances(player_rating, opponent_rating)
            for opponent_rating in opponent_ratings
        ]
        return Decimal(
            sum(
                chance[0] * Decimal(Result.GAIN.points(point_values))
                + chance[1] * Decimal(Result.LOSS.points(point_values))
                for chance in chances
            )
        )

    @staticmethod
    def win_chances(player_rating: int, opponent_rating: int) -> tuple[Decimal, Decimal]:
        difference = abs(player_rating - opponent_rating)
        lower_bounds: list[int] = [
            4, 11, 17, 18, 26, 33, 40, 47, 54, 62, 69, 77, 84, 92, 99,
            107, 114, 122, 130, 138, 146, 154, 163, 171, 180, 189, 198, 207,
            216, 226, 236, 246, 257, 268, 279, 291, 303, 316, 329, 345, 358,
            375, 392, 412, 433, 457, 485, 518, 560, 620, 736,
        ]
        difference_index = bisect_right(lower_bounds, difference) - 1
        high = Decimal(0.5) + Decimal('0.01') * difference_index
        low = 1 - high
        if player_rating >= opponent_rating:
            return high, low
        else:
            return low, high


@register_tie_break
class AveragePerfectPerformanceTieBreak(AbstractTieBreak):
    """The average of the Perfect Tournament Performances
    of the opponents (only those who played).
    See FIDE Hand book C.07.10.5."""

    @property
    def name(self) -> str:
        return _('Average perfect performance of opponents')

    @staticmethod
    def identifier() -> str:
        return 'AVERAGE_PERFECT_PERFORMANCE'

    @property
    def acronym(self) -> str:
        return 'APPO'

    @property
    def short_name(self) -> str:
        return _(
            'Avg. Perfect Perf. *** '
            'SHORT NAME FOR AVERAGE PERFECT PERFORMANCE'
        )

    def compute_player_value(
            self,
            player: 'Player',
            *,
            after_round: int | None,
    ) -> int:
        if after_round is None:
            after_round = max(player.pairings)
        pairings: list[Pairing] = [
            pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round and pairing.played
        ]
        ptp_tie_break = PerfectTournamentPerformanceTieBreak()
        tournament: 'Tournament' = player.tournament
        ptp = [
            ptp_tie_break.compute_player_value(
                tournament.players_by_id[pairing.opponent_id],
                after_round=after_round,
            )
            for pairing in pairings
        ]

        if not ptp:
            return 0
        return StaticUtils.round_ranking(sum(ptp) / len(ptp))


@register_tie_break
class DirectEncounterTieBreak(AbstractTieBreak):
    """Direct Encounter score.
    Options:
      - EXCLUDE_IDS: List of player ids to not take into account.
      - PLAYED_MODIFIER: When False and the tournament is a Swiss tournament, all forfeit games
    will be excluded from consideration.
    See FIDE Handbook C.07.6."""

    @property
    def name(self) -> str:
        return _('Direct encounter')

    @staticmethod
    def identifier() -> str:
        return 'DIRECT_ENCOUNTER'

    @property
    def acronym(self) -> str:
        return 'DE'

    @property
    def short_name(self) -> str:
        return _('Direct encounter')

    @staticmethod
    def available_options() -> list[type[AbstractTieBreakOption]]:
        return [
            ExcludeIdsTieBreakOption,
            PlayedModifierTieBreakOption,
        ]

    @property
    def is_displayable(self) -> bool:
        # tuple[float, bool] is not displayable
        return False

    def compute_player_value(
        self,
        player: 'Player',
        *,
        after_round: int | None,
    ) -> tuple[float, bool]:
        """ If all players with the same number of points as *player* before round
        *after_round* have played each other, returns the score *player* achieved against
        all tied opponents in the form (score, True).
        If not, returns the score achieved and a number of wins against all missing opponents
        in the form (virtual_score, False).
        If the second member is True, either some ties are broken correctly, or
        some players cannot be untied this way.
        If the second member is False, some ties might be broken, but there is no guarantee.
        """
        tournament: 'Tournament' = player.tournament
        exclude_ids, played_modifier = self.get_option_values()
        if after_round is None:
            after_round = max(player.pairings)
        final_points = player.points_after(after_round)
        tied_opponents: dict[int, Player] = {
            opponent_id: opponent
            for opponent_id, opponent in tournament.players_by_id.items()
            if opponent_id != player.id
        }
        tied_opponents = {
            opponent_id: opponent
            for opponent_id, opponent in tied_opponents.items()
            if opponent_id is not None
            and opponent.points_after(after_round) == final_points
        }
        if exclude_ids is not None:
            tied_opponents = {
                opponent.id: opponent
                for opponent in tied_opponents.values()
                if opponent.id not in exclude_ids
            }
        tied_pairings: dict[int, Pairing] = {
            pairing.opponent_id: pairing
            for pairing in player.pairings.values()
            if pairing.opponent_id in tied_opponents
        }
        if tournament.pairing.swiss and not played_modifier:
            tied_pairings = {
                opponent_id: pairing
                for opponent_id, pairing in tied_pairings.items()
                if pairing.result not in (
                    Result.FORFEIT_GAIN, Result.DOUBLE_FORFEIT, Result.FORFEIT_LOSS
                )
            }
        if len(tied_pairings) == len(tied_opponents):
            return sum(
                pairing.result.points(tournament.point_values)
                for pairing in tied_pairings.values()
            ), True
        virtual_pairings: dict[int, Pairing] = {
            opponent_id: Pairing(None, opponent_id, Result.GAIN)
            for opponent_id in tied_opponents
            if opponent_id not in tied_pairings
        }
        return sum(
            pairing.result.points(tournament.point_values)
            for pairing in list(tied_pairings.values()) + list(virtual_pairings.values())
        ), False
