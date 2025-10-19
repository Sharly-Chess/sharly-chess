from abc import ABC, abstractmethod
from contextlib import suppress
from functools import cache, lru_cache, cached_property
from math import floor
from types import UnionType
from typing import TYPE_CHECKING, Any

from common.exception import OptionError
from common.i18n import _
from data.pairing import Pairing
from data.pairings import PairingSystem
from data.pairings.systems import RoundRobinPairingSystem, SwissPairingSystem
from data.player import Player
from data.tie_breaks import TieBreak, TieBreakOption
from data.tie_breaks.categories import TieBreakCategory
from data.tie_breaks.tie_breaks import (
    TournamentPerformanceRatingTieBreak,
    KashdanTieBreak,
    StandardBuchholzTieBreak,
)
from plugins.ffe import PLUGIN_NAME
from utils import StaticUtils
from utils.entity import IdentifiableEntity, EntityManager
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


class BasePapiTieBreak(TieBreak, ABC):
    """Implementation of the tie-breaks as in Papi.
    Computation inaccuracies are reproduced"""

    @staticmethod
    @abstractmethod
    def base_tie_break_type() -> type[TieBreak]:
        """Tie-break of the core matching the re-implementation of Papi."""

    @cached_property
    def base_tie_break(self) -> TieBreak:
        return self.base_tie_break_type()()

    @classmethod
    def static_id(cls) -> str:
        return f'{PLUGIN_NAME}-PAPI_{cls.base_tie_break_type().static_id()}'

    @classmethod
    def static_name(cls) -> str:
        return f'{cls.base_tie_break_type().static_name()} (PAPI)'

    @property
    def full_name(self) -> str:
        return f'{self.base_full_name} (PAPI)'

    @property
    def base_help_text(self) -> str:
        return _('The [{tie_break}] tie-break as implemented in Papi.').format(
            tie_break=self.base_full_name
        )

    @property
    def base_full_name(self) -> str:
        """Name of the tie-break to display in the full name and the help text."""
        return self.base_tie_break_type().static_name()

    @property
    def category(self) -> TieBreakCategory:
        return self.base_tie_break.category

    @property
    def forbidden_pairing_systems(self) -> list[PairingSystem]:
        return self.base_tie_break.forbidden_pairing_systems


class PapiPerformanceTieBreak(BasePapiTieBreak):
    @staticmethod
    def base_tie_break_type() -> type[TieBreak]:
        return TournamentPerformanceRatingTieBreak

    @property
    def base_acronym(self) -> str:
        return 'Perf'

    def compute_player_value(self, player: 'Player', *, after_round: int) -> float:
        tournament: 'Tournament' = player.tournament
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
        max_score = len(ratings) * Result.WIN.points(tournament.point_values)
        average = sum(ratings) / len(ratings)
        fractional_score = score / max_score
        bonus = papi_performance_bonus(fractional_score)
        return round(average + bonus)


class PapiKashdanTieBreak(BasePapiTieBreak):
    @staticmethod
    def base_tie_break_type() -> type[TieBreak]:
        return KashdanTieBreak

    @property
    def base_acronym(self) -> str:
        return 'Ka.'

    def compute_player_value(self, player: 'Player', *, after_round: int) -> float:
        """Legacy: unplayed rounds are counted"""

        pairings: list[Pairing] = [
            pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        ]
        score_by_result: dict[Result, float] = {
            Result.WIN: 4,
            Result.UNRATED_WIN: 4,
            Result.DRAW: 2,
            Result.UNRATED_DRAW: 2,
            Result.LOSS: 1,
            Result.UNRATED_LOSS: 1,
        }
        return sum(pairing.result.points(score_by_result) for pairing in pairings)


# -----------------------------------------------------------------------------
# Buchholz
# -----------------------------------------------------------------------------


class PapiBuchholzType(IdentifiableEntity, ABC):
    @property
    @abstractmethod
    def full_name(self) -> str:
        """Full name of the tie-break in Papi for this type."""

    @property
    @abstractmethod
    def acronym(self) -> str:
        """Acronym of the tie-break in Papi."""

    @property
    @abstractmethod
    def use_bottom_cut(self) -> bool:
        """Defines if the bottom cut should be used."""

    @property
    @abstractmethod
    def use_top_cut(self) -> bool:
        """Defines if the top cut should be used."""


class StandardPapiBuchholzType(PapiBuchholzType):
    @staticmethod
    def static_id() -> str:
        return 'STANDARD'

    @staticmethod
    def static_name() -> str:
        return _('Standard')

    @property
    def full_name(self) -> str:
        return _('Buchholz')

    @property
    def acronym(self) -> str:
        return 'Bu.'

    @property
    def use_bottom_cut(self) -> bool:
        return False

    @property
    def use_top_cut(self) -> bool:
        return False


class CutPapiBuchholzType(PapiBuchholzType):
    @staticmethod
    def static_id() -> str:
        return 'CUT'

    @staticmethod
    def static_name() -> str:
        return _('Cut *** TIE BREAK VARIATION')

    @property
    def full_name(self) -> str:
        return _('Buchholz cut')

    @property
    def acronym(self) -> str:
        return 'Tr.'

    @property
    def use_bottom_cut(self) -> bool:
        return True

    @property
    def use_top_cut(self) -> bool:
        return False


class MedianPapiBuchholzType(PapiBuchholzType):
    @staticmethod
    def static_id() -> str:
        return 'MEDIAN'

    @staticmethod
    def static_name() -> str:
        return _('Median')

    @property
    def full_name(self) -> str:
        return _('Median Buchholz')

    @property
    def acronym(self) -> str:
        return 'Me.'

    @property
    def use_bottom_cut(self) -> bool:
        return True

    @property
    def use_top_cut(self) -> bool:
        return True


class PapiBuchholzTypeManager(EntityManager[PapiBuchholzType]):
    def entity_types(self) -> list[type[PapiBuchholzType]]:
        return [
            StandardPapiBuchholzType,
            CutPapiBuchholzType,
            MedianPapiBuchholzType,
        ]


class PapiBuchholzTypeOption(TieBreakOption):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-PAPI_BUCHHOLZ_TYPE'

    @property
    def template_name(self) -> str:
        return '/ffe_papi_buchholz_type_option.html'

    @property
    def template_file_stem(self) -> str:
        return ''

    @property
    def variation_acronym(self) -> str:
        return ''

    @property
    def variation_name(self) -> str:
        return ''

    @property
    def variation_help_text(self) -> str:
        return ''

    @property
    def type(self) -> type | UnionType:
        return str

    @property
    def default_value(self) -> Any:
        return StandardPapiBuchholzType.static_id()

    @property
    def buchholz_type_options(self) -> dict[str, str]:
        return {
            buchholz_type.id: buchholz_type.name
            for buchholz_type in PapiBuchholzTypeManager().objects()
        }

    @cached_property
    def buchholz_type(self) -> PapiBuchholzType:
        return PapiBuchholzTypeManager().get_object(self.value)

    def validate(self):
        super().validate()
        try:
            __ = self.buchholz_type
        except KeyError:
            raise OptionError(f'Unknown Buchholz type: {self.value}', self)


class PapiBuchholzTieBreak(BasePapiTieBreak):
    @staticmethod
    def base_tie_break_type() -> type[TieBreak]:
        return StandardBuchholzTieBreak

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [PapiBuchholzTypeOption]

    @cached_property
    def type(self) -> PapiBuchholzType:
        return self._get_option(PapiBuchholzTypeOption).buchholz_type

    @property
    def base_acronym(self) -> str:
        return self.type.acronym

    @property
    def base_full_name(self) -> str:
        return self.type.full_name

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
                Result.FORFEIT_WIN
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
                return dummy + Result.WIN.points(player.point_values)
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

    def compute_player_value(self, player: Player, *, after_round: int) -> float:
        tournament: 'Tournament' = player.tournament
        cut = self._papi_buchholz_cut(tournament.rounds)
        cut_top = cut if self.type.use_top_cut else 0
        cut_btm = cut if self.type.use_bottom_cut else 0
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


class PapiSumOfBuchholzTieBreak(PapiBuchholzTieBreak):
    @property
    def acronym(self) -> str:
        return 'SBh'

    def compute_player_value(self, player: 'Player', *, after_round: int) -> float:
        tournament: 'Tournament' = player.tournament
        opponents: list[Player | None] = [
            tournament.players_by_id.get(pairing.opponent_id)
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round and pairing.opponent_id is not None
        ]
        tie_break = PapiBuchholzTieBreak()
        return sum(
            tie_break.compute_player_value(opponent, after_round=after_round)
            for opponent in opponents
            if opponent is not None
        )
