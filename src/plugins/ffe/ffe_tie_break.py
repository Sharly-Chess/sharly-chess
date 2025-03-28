from abc import ABC, abstractmethod
from contextlib import suppress
from functools import cache, lru_cache
from math import floor

from common.i18n import _
from data.pairing import Pairing
from data.player import Player
from data.tie_break import AbstractTieBreak
from data.tournament import Tournament
from data.util import TournamentPairing, Result, StaticUtils


@lru_cache(maxsize=32)
def papi_performance_bonus(fractional_score: float) -> int | float:
    performance_table = StaticUtils.PERFORMANCE_TABLE[:-1] + [677, 677]
    percent = 100 * fractional_score
    index = floor(abs(50 - percent))
    percent_int = floor(percent)
    bonus = performance_table[index]
    smaller_difference = percent - percent_int
    if smaller_difference > 0:
        smaller_difference *= performance_table[index + 1] - bonus
        bonus += smaller_difference
    if fractional_score < 0.5:
        bonus *= -1
    return bonus


class AbstractPapiTieBreak(AbstractTieBreak, ABC):
    """Implementation of the tie-breaks as in Papi.
    Computation inaccuracies are reproduced"""

    @property
    @abstractmethod  # AS the usage is for Papi, papi_id has to be implemented
    def papi_id(self) -> str:
        pass


class AbstractPapiBuchholzTieBreak(AbstractPapiTieBreak, ABC):
    @staticmethod
    def _papi_adjusted_score(
        player: 'Player',
        *,
        after_round: int,
    ) -> float:
        """Legacy: Unplayed rounds are counted as draws"""
        tournament: 'Tournament' = player.tournament
        if after_round is None:
            after_round = max(player.pairings)
        if tournament.pairing == TournamentPairing.BERGER:
            return player.points_after(after_round)
        score = 0
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
        player: 'Player',
        pairing: Pairing,
        *,
        after_round: int = 1,
        round_index: int = 1,
    ) -> float:
        """Legacy: uses round_index for the computation"""
        dummy = player.points_before(round_index) + Result.DRAW.points(player.point_values) * (
                after_round - round_index)
        match pairing.result:
            case Result.FORFEIT_GAIN | Result.PAIRING_ALLOCATED_BYE | Result.FULL_POINT_BYE:
                return dummy + Result.LOSS.points(player.point_values)
            case Result.HALF_POINT_BYE:
                return dummy + Result.DRAW.points(player.point_values)
            case Result.ZERO_POINT_BYE | Result.FORFEIT_LOSS | Result.DOUBLE_FORFEIT | Result.NO_RESULT:
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
        if tournament.pairing == TournamentPairing.BERGER:
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
            should_add_dummy = tournament.pairing.swiss and pairing.unplayed

            if should_add_dummy:
                dummy_points = self._papi_dummy_score(
                    player, pairing, after_round=after_round, round_index=round_index
                )
                scores.append(dummy_points)
                continue
            opponent: Player = tournament.players_by_id[pairing.opponent_id]
            if tournament.pairing.swiss:
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


class PapiBuchholzTieBreak(AbstractPapiBuchholzTieBreak):
    @property
    def name(self) -> str:
        return _('Buchholz')

    @property
    def id(self) -> str:
        return 'PAPI_BUCHHOLZ'

    @property
    def papi_id(self) -> str:
        return 'Solkoff'

    @property
    def acronym(self) -> str:
        return _('Bu. *** ACRONYM FOR PAPI BUCHHOLZ')

    @property
    def short_name(self) -> str:
        return _('Buchholz')

    def compute_player_value(
        self,
        player: 'Player',
        *,
        after_round: int | None,
    ) -> float:
        return self.compute_papi_buchholz_player_value(
            player, after_round=after_round
        )


class PapiBuchholzCutBottomTieBreak(AbstractPapiBuchholzTieBreak):
    @property
    def name(self) -> str:
        return _('Buchholz cut bottom')

    @property
    def id(self) -> str:
        return 'PAPI_BUCHHOLZ_CUT_BOTTOM'

    @property
    def papi_id(self) -> str:
        return 'Brésilien'

    @property
    def acronym(self) -> str:
        return _('Tr. *** ACRONYM FOR PAPI BUCHHOLZ CUT BOTTOM')

    @property
    def short_name(self) -> str:
        return _('Tr. Buchholz *** SHORT NAME FOR PAPI BUCHHOLZ CUT BOTTOM')

    def compute_player_value(
            self,
            player: 'Player',
            *,
            after_round: int | None,
    ) -> float:
        return self.compute_papi_buchholz_player_value(
            player, after_round=after_round, use_cut_btm=True
        )


class PapiMedianBuchholzTieBreak(AbstractPapiBuchholzTieBreak):
    @property
    def name(self) -> str:
        return _('Median Buchholz')

    @property
    def id(self) -> str:
        return 'PAPI_MEDIAN_BUCHHOLZ'

    @property
    def papi_id(self) -> str:
        return 'Harkness'

    @property
    def acronym(self) -> str:
        return _('Me. *** ACRONYM FOR PAPI MEDIAN BUCHHOLZ')

    @property
    def short_name(self) -> str:
        return _('Me. Buchholz *** SHORT NAME FOR PAPI MEDIAN BUCHHOLZ')

    def compute_player_value(
            self,
            player: 'Player',
            *,
            after_round: int | None,
    ) -> float:
        return self.compute_papi_buchholz_player_value(
            player,
            after_round=after_round,
            use_cut_top=True,
            use_cut_btm=True,
        )


class PapiPerformanceTieBreak(AbstractPapiTieBreak):
    @property
    def name(self) -> str:
        return _('Performance')

    @property
    def id(self) -> str:
        return 'PAPI_PERFORMANCE'

    @property
    def papi_id(self) -> str:
        return 'Performance'

    @property
    def acronym(self) -> str:
        return _('Perf *** ACRONYM FOR PAPI PERFORMANCE')

    @property
    def short_name(self) -> str:
        return _('Performance')

    def compute_player_value(
            self,
            player: 'Player',
            *,
            after_round: int | None,
    ) -> float:
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
                rating = min(
                    player.estimation + 400,
                    max(player.estimation - 400,
                        opponent.estimation))
                ratings.append(rating)
                score += pairing.result.points(tournament.point_values)
        if not ratings:
            return 0
        max_score = len(ratings) * Result.GAIN.points(tournament.point_values)
        average = sum(ratings) / len(ratings)
        fractional_score = score / max_score
        bonus = papi_performance_bonus(fractional_score)
        return round(average + bonus)


class PapiSumOfBuchholzTieBreak(AbstractPapiTieBreak):
    @property
    def name(self) -> str:
        return _('Sum of Buchholz')

    @property
    def id(self) -> str:
        return 'PAPI_BUCHHOLZ_SUM'

    @property
    def papi_id(self) -> str:
        return 'SommeDesBuchholz'

    @property
    def acronym(self) -> str:
        return _('SBh *** ACRONYM FOR PAPI SUM OF BUCHHOLZ')

    @property
    def short_name(self) -> str:
        return _('Bu. sum *** SHORT NAME FOR SUM OF BUCHHOLZ')

    def compute_player_value(
            self,
            player: 'Player',
            *,
            after_round: int | None,
    ) -> float:
        tournament: 'Tournament' = player.tournament
        if after_round is None:
            after_round = max(player.pairings)
        opponents: list[Player | None] = [
            tournament.players_by_id.get(pairing.opponent_id)
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        ]
        tie_break = PapiBuchholzTieBreak()
        return sum(
            tie_break.compute_player_value(opponent, after_round=after_round)
            for opponent in opponents if opponent is not None
        )


class PapiKashdanTieBreak(AbstractPapiTieBreak):
    @property
    def name(self) -> str:
        return _('Kashdan')

    @property
    def id(self) -> str:
        return 'PAPI_KASHDAN'

    @property
    def papi_id(self) -> str:
        return 'Kashdan'

    @property
    def acronym(self) -> str:
        return _('Ka. *** ACRONYM FOR PAPI KASHDAN')

    @property
    def short_name(self) -> str:
        return _('Kashdan')

    def compute_player_value(
            self,
            player: 'Player',
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
        score_by_result: dict[Result, int] = {
            Result.GAIN: 4,
            Result.UNRATED_GAIN: 4,
            Result.DRAW: 2,
            Result.UNRATED_DRAW: 2,
            Result.LOSS: 1,
            Result.UNRATED_LOSS: 1,
        }
        return sum(pairing.result.points(score_by_result) for pairing in pairings)
