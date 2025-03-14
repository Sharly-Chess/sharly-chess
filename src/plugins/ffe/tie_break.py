from abc import ABC, abstractmethod
from contextlib import suppress
from typing import Literal

from common.i18n import _
from data.pairing import Pairing
from data.player import Player
from data.tie_break import AbstractTieBreak
from data.tournament import Tournament
from data.util import TournamentPairing, Result, performance_bonus


class AbstractPapiTieBreak(AbstractTieBreak, ABC):
    @property
    @abstractmethod
    def papi_id(self) -> str:
        pass

    @staticmethod
    def _papi_adjusted_score(
        player: 'Player',
        tournament: 'Tournament',
        max_round: int,
    ) -> float:
        """Legacy: Unplayed rounds are counted as draws"""
        if max_round is None:
            max_round = max(player.pairings)
        if tournament.pairing == TournamentPairing.BERGER:
            return player.points_after(max_round)
        score = 0
        for round_index, pairing in player.pairings.items():
            if round_index > max_round:
                continue
            if pairing.unplayed:
                score += Result.DRAW.points(tournament.point_values)
                continue
            if pairing.requested_bye:
                if all(
                        p.voluntary_unplayed
                        for index, p in player.pairings.items()
                        if round_index < index <= max_round
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
        max_round: int = 1,
        round_index: int = 1,
        dummy_type: Literal['BH'] | Literal['SB'] = 'BH',
    ) -> float | tuple[float, Result]:
        """Legacy: uses round_index for the computation"""
        if dummy_type == 'BH':
            dummy = player.points_before(round_index) + Result.DRAW.points(player.point_values) * (
                        max_round - round_index)
            match pairing.result:
                case Result.FORFEIT_GAIN | Result.PAIRING_ALLOCATED_BYE | Result.FULL_POINT_BYE:
                    return dummy + Result.LOSS.points(player.point_values)
                case Result.HALF_POINT_BYE:
                    return dummy + Result.DRAW.points(player.point_values)
                case Result.ZERO_POINT_BYE | Result.FORFEIT_LOSS | Result.DOUBLE_FORFEIT | Result.NO_RESULT:
                    return dummy + Result.GAIN.points(player.point_values)
                case _:
                    raise ValueError(f'{pairing.result=}')
        elif dummy_type == 'SB':
            dummy = player.points_after(max_round)
            match pairing.result:
                case Result.FORFEIT_GAIN | Result.PAIRING_ALLOCATED_BYE | Result.FULL_POINT_BYE:
                    return dummy, Result.GAIN
                case Result.HALF_POINT_BYE:
                    return dummy, Result.DRAW
                case Result.ZERO_POINT_BYE | Result.FORFEIT_LOSS | Result.DOUBLE_FORFEIT | Result.NO_RESULT:
                    return dummy, Result.LOSS
                case _:
                    return dummy, pairing.result
        raise ValueError(f'{dummy_type=}')

    @staticmethod
    def papi_buchholz_cut(tournament_rounds: int) -> int:
        if tournament_rounds <= 7:
            return 1
        elif tournament_rounds <= 12:
            return 2
        return 3

    def _compute_papi_buchholz_player_value(
        self,
        player: Player,
        tournament: Tournament,
        max_round: int | None,
        cut_top: int = 0,
        cut_btm: int = 0,
    ) -> float:
        if max_round is None:
            max_round = max(player.pairings)
        if cut_top + cut_btm >= max_round:
            return 0
        pairings: dict[int, Pairing] = {
            round_index: pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= max_round
        }
        if tournament.pairing == TournamentPairing.BERGER:
            return sum(
                self._papi_adjusted_score(
                    tournament.players_by_id[pairing.opponent_id],
                    tournament,
                    max_round,
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
                    player, pairing, max_round, round_index
                )
                scores.append(dummy_points)
                continue
            opponent: Player = tournament.players_by_id[pairing.opponent_id]
            if tournament.pairing.swiss:
                opponent_adjusted_score = self._papi_adjusted_score(
                    opponent, tournament, max_round
                )
            else:
                opponent_adjusted_score = opponent.points_after(max_round)
            scores.append(opponent_adjusted_score)
        voluntary_unplayed = sorted(voluntary_unplayed)
        scores = sorted(scores)
        scores = voluntary_unplayed + scores

        if cut_top:
            return sum(scores[cut_btm:-cut_top])
        return sum(scores[cut_btm:])


class PapiBuchholzTieBreak(AbstractPapiTieBreak):
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

    def compute_player_value(
        self,
        player: 'Player',
        tournament: 'Tournament',
        max_round: int | None = None
    ) -> float:
        return self._compute_papi_buchholz_player_value(
            player, tournament, max_round
        )


class PapiBuchholzCutBottomTieBreak(AbstractPapiTieBreak):
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

    def compute_player_value(
            self,
            player: 'Player',
            tournament: 'Tournament',
            max_round: int | None = None
    ) -> float:
        return self._compute_papi_buchholz_player_value(
            player,
            tournament,
            max_round,
            cut_btm=self.papi_buchholz_cut(tournament.rounds),
        )


class PapiMedianBuchholzTieBreak(AbstractPapiTieBreak):
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

    def compute_player_value(
            self,
            player: 'Player',
            tournament: 'Tournament',
            max_round: int | None = None
    ) -> float:
        cut = self.papi_buchholz_cut(tournament.rounds)
        return self._compute_papi_buchholz_player_value(
            player, tournament, max_round, cut, cut
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

    def compute_player_value(
            self,
            player: 'Player',
            tournament: 'Tournament',
            max_round: int | None = None
    ) -> float:
        if max_round is None:
            max_round = max(player.pairings)
        pairings: list[Pairing] = [
            pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= max_round and pairing.played
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
        bonus = performance_bonus(fractional_score, papi_legacy=True)
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

    def compute_player_value(
            self,
            player: 'Player',
            tournament: 'Tournament',
            max_round: int | None = None
    ) -> float:
        if max_round is None:
            max_round = max(player.pairings)
        opponents: list[Player | None] = [
            tournament.players_by_id.get(pairing.opponent_id)
            for round_index, pairing in player.pairings.items()
            if round_index <= max_round
        ]
        tie_break = PapiBuchholzTieBreak()
        return sum(
            tie_break.compute_player_value(opponent, tournament, max_round)
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

    def compute_player_value(
            self,
            player: 'Player',
            tournament: 'Tournament',
            max_round: int | None = None
    ) -> float:
        """Legacy: unplayed rounds are counted"""
        if max_round is None:
            max_round = max(player.pairings)

        pairings: list[Pairing] = [
            pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= max_round
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
