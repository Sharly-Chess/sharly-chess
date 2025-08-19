from abc import ABC, abstractmethod
from contextlib import suppress
from functools import cache, lru_cache
from math import floor
from typing import TYPE_CHECKING

from common import experimental_features_enabled
from common.i18n import _
from data.pairing import Pairing
from data.pairings.systems import RoundRobinPairingSystem, SwissPairingSystem
from data.player import Player
from data.tie_breaks import TieBreak
from data.tie_breaks.tie_breaks import BuchholzTieBreak, PerformanceTieBreak
from plugins.ffe import PLUGIN_NAME
from utils import StaticUtils
from utils.enum import Result

if TYPE_CHECKING:
    from data.tournament import Tournament


@lru_cache(maxsize=32)
def papi_performance_bonus(fractional_score: float) -> int | float:
    performance_table = StaticUtils.PERFORMANCE_TABLE[:-1] + [677, 677]
    percent = 100 * fractional_score
    index = floor(abs(50 - percent))
    percent_int = floor(percent)
    bonus = float(performance_table[index])
    smaller_difference = percent - percent_int
    if smaller_difference > 0:
        smaller_difference *= performance_table[index + 1] - bonus
    bonus += smaller_difference
    if fractional_score < 0.5:
        bonus *= -1
    return bonus


class FfeTieBreak(TieBreak, ABC):
    """Implementation of the tie-breaks as in Papi.
    Computation inaccuracies are reproduced"""

    @classmethod
    def static_id(cls) -> str:
        return f'{PLUGIN_NAME}-{cls.sub_id()}'

    @staticmethod
    @abstractmethod
    def sub_id() -> str:
        pass

    @classmethod
    def static_name(cls) -> str:
        if not experimental_features_enabled():
            return cls.sub_name()
        return _('{tie_break} (Papi compatible)').format(tie_break=cls.sub_name())

    @staticmethod
    @abstractmethod
    def sub_name() -> str:
        pass


class PapiBuchholzTieBreak(FfeTieBreak, BuchholzTieBreak, ABC):
    @staticmethod
    def _papi_adjusted_score(
        player: Player,
        *,
        after_round: int,
    ) -> float:
        """Legacy: Unplayed rounds are counted as draws"""
        assert player.tournament is not None
        tournament: 'Tournament' = player.tournament
        if after_round is None:
            after_round = max(player.pairings)
        if tournament.pairing_system == RoundRobinPairingSystem():
            return player.points_after(after_round)
        score = 0.0
        for round_index, pairing in player.pairings.items():
            if round_index > after_round:
                continue
            if pairing.unplayed:
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
    def _papi_dummy_score(
        player: Player,
        pairing: Pairing,
        *,
        after_round: int = 1,
        round_index: int = 1,
    ) -> float:
        """Legacy: uses round_index for the computation"""
        dummy = player.points_before(round_index) + Result.DRAW.points(
            player.point_values
        ) * (after_round - round_index)
        match pairing.result:
            case (
                Result.FORFEIT_GAIN
                | Result.PAIRING_ALLOCATED_BYE
                | Result.FULL_POINT_BYE
            ):
                return dummy + Result.LOSS.points(player.point_values)
            case Result.HALF_POINT_BYE:
                return dummy + Result.DRAW.points(player.point_values)
            case (
                Result.ZERO_POINT_BYE
                | Result.FORFEIT_LOSS
                | Result.DOUBLE_FORFEIT
                | Result.NO_RESULT
            ):
                return dummy + Result.GAIN.points(player.point_values)
            case _:
                raise ValueError(f'{pairing.result=}')

    @staticmethod
    @cache
    def _papi_buchholz_cut(tournament_rounds: int) -> int:
        if tournament_rounds <= 7:
            return 1
        elif tournament_rounds <= 12:
            return 2
        return 3

    def compute_papi_buchholz_player_value(
        self,
        player: Player,
        *,
        after_round: int | None,
        use_cut_top: bool = False,
        use_cut_btm: bool = False,
    ) -> float:
        if after_round is None:
            after_round = max(player.pairings)
        assert player.tournament is not None
        tournament: 'Tournament' = player.tournament
        cut = self._papi_buchholz_cut(tournament.rounds)
        cut_top = cut if use_cut_top else 0
        cut_btm = cut if use_cut_btm else 0
        if cut_top + cut_btm >= after_round:
            return 0
        pairings: dict[int, Pairing] = {
            round_index: pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        }
        pairing_system = tournament.pairing_system
        if pairing_system == RoundRobinPairingSystem():
            return sum(
                self._papi_adjusted_score(
                    tournament.players_by_id[pairing.opponent_id],
                    after_round=after_round,
                )
                for pairing in pairings.values()
                if pairing.opponent_id is not None
            )
        scores: list[float] = []
        voluntary_unplayed: list[float] = []
        for round_index, pairing in pairings.items():
            should_add_dummy = (
                pairing_system == SwissPairingSystem() and pairing.unplayed
            )
            if should_add_dummy:
                dummy_points = self._papi_dummy_score(
                    player, pairing, after_round=after_round, round_index=round_index
                )
                scores.append(dummy_points)
                continue
            assert pairing.opponent_id is not None
            opponent: Player = tournament.players_by_id[pairing.opponent_id]
            if pairing_system == SwissPairingSystem():
                opponent_adjusted_score = self._papi_adjusted_score(
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


class PapiStandardBuchholzTieBreak(PapiBuchholzTieBreak):
    @staticmethod
    def sub_name() -> str:
        return _('Buchholz')

    @staticmethod
    def sub_id() -> str:
        return 'PAPI_BUCHHOLZ'

    @property
    def acronym(self) -> str:
        return _('Bu. *** ACRONYM FOR PAPI BUCHHOLZ')

    @property
    def short_name(self) -> str:
        return _('Buchholz')

    def compute_player_value(
        self,
        player: Player,
        *,
        after_round: int | None,
    ) -> float:
        return self.compute_papi_buchholz_player_value(player, after_round=after_round)


class PapiBuchholzCutBottomTieBreak(PapiBuchholzTieBreak):
    @staticmethod
    def sub_name() -> str:
        return _('Buchholz cut bottom')

    @staticmethod
    def sub_id() -> str:
        return 'PAPI_BUCHHOLZ_CUT_BOTTOM'

    @property
    def acronym(self) -> str:
        return _('Tr. *** ACRONYM FOR PAPI BUCHHOLZ CUT BOTTOM')

    @property
    def short_name(self) -> str:
        return _('Tr. Buchholz *** SHORT NAME FOR PAPI BUCHHOLZ CUT BOTTOM')

    def compute_player_value(
        self,
        player: Player,
        *,
        after_round: int | None,
    ) -> float:
        return self.compute_papi_buchholz_player_value(
            player, after_round=after_round, use_cut_btm=True
        )


class PapiMedianBuchholzTieBreak(PapiBuchholzTieBreak):
    @staticmethod
    def sub_name() -> str:
        return _('Median Buchholz')

    @staticmethod
    def sub_id() -> str:
        return 'PAPI_MEDIAN_BUCHHOLZ'

    @property
    def acronym(self) -> str:
        return _('Me. *** ACRONYM FOR PAPI MEDIAN BUCHHOLZ')

    @property
    def short_name(self) -> str:
        return _('Me. Buchholz *** SHORT NAME FOR PAPI MEDIAN BUCHHOLZ')

    def compute_player_value(
        self,
        player: Player,
        *,
        after_round: int | None,
    ) -> float:
        return self.compute_papi_buchholz_player_value(
            player,
            after_round=after_round,
            use_cut_top=True,
            use_cut_btm=True,
        )


class PapiPerformanceTieBreak(FfeTieBreak, PerformanceTieBreak):
    @staticmethod
    def sub_name() -> str:
        return _('Performance')

    @staticmethod
    def sub_id() -> str:
        return 'PAPI_PERFORMANCE'

    @staticmethod
    def static_papi_id() -> str:
        return 'Performance'

    @property
    def acronym(self) -> str:
        return _('Perf *** ACRONYM FOR PAPI PERFORMANCE')

    @property
    def short_name(self) -> str:
        return _('Performance')

    def compute_player_value(
        self,
        player: Player,
        *,
        after_round: int | None,
    ) -> float:
        assert player.tournament is not None
        tournament: 'Tournament' = player.tournament
        if after_round is None:
            after_round = max(player.pairings)
        pairings: list[Pairing] = [
            pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round and pairing.played
        ]
        ratings = []
        score = 0.0
        for pairing in pairings:
            assert pairing.opponent_id is not None
            opponent = tournament.players_by_id[pairing.opponent_id]
            with suppress(KeyError):
                rating = min(
                    player.estimation + 400,
                    max(player.estimation - 400, opponent.estimation),
                )
                ratings.append(rating)
                score += pairing.result.points(tournament.point_values)
        if not ratings:
            return 0
        max_score = len(ratings) * Result.GAIN.points(tournament.point_values)
        average = sum(ratings) / len(ratings)
        fractional_score = score / max_score
        bonus = papi_performance_bonus(fractional_score)
        return round(average + bonus)


class PapiSumOfBuchholzTieBreak(PapiBuchholzTieBreak):
    @staticmethod
    def sub_name() -> str:
        return _('Sum of Buchholz')

    @staticmethod
    def sub_id() -> str:
        return 'PAPI_BUCHHOLZ_SUM'

    @property
    def acronym(self) -> str:
        return _('SBh *** ACRONYM FOR PAPI SUM OF BUCHHOLZ')

    @property
    def short_name(self) -> str:
        return _('Bu. sum *** SHORT NAME FOR SUM OF BUCHHOLZ')

    def compute_player_value(
        self,
        player: Player,
        *,
        after_round: int | None,
    ) -> float:
        assert player.tournament is not None
        tournament: 'Tournament' = player.tournament
        if after_round is None:
            after_round = max(player.pairings)
        opponents: list[Player | None] = [
            tournament.players_by_id.get(pairing.opponent_id)
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round and pairing.opponent_id is not None
        ]
        tie_break = PapiStandardBuchholzTieBreak()
        return sum(
            tie_break.compute_player_value(opponent, after_round=after_round)
            for opponent in opponents
            if opponent is not None
        )


class PapiKashdanTieBreak(FfeTieBreak):
    @staticmethod
    def sub_name() -> str:
        return _('Kashdan')

    @staticmethod
    def sub_id() -> str:
        return 'PAPI_KASHDAN'

    @property
    def acronym(self) -> str:
        return _('Ka. *** ACRONYM FOR PAPI KASHDAN')

    @property
    def short_name(self) -> str:
        return _('Kashdan')

    def compute_player_value(
        self,
        player: Player,
        *,
        after_round: int | None,
    ) -> float:
        """Legacy: unplayed rounds are counted"""
        if after_round is None:
            after_round = max(player.pairings)

        pairings: list[Pairing] = [
            pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        ]
        score_by_result: dict[Result, float] = {
            Result.GAIN: 4,
            Result.UNRATED_GAIN: 4,
            Result.DRAW: 2,
            Result.UNRATED_DRAW: 2,
            Result.LOSS: 1,
            Result.UNRATED_LOSS: 1,
        }
        return sum(pairing.result.points(score_by_result) for pairing in pairings)
