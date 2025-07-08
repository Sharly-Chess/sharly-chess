from abc import ABC, abstractmethod
from functools import cached_property, partial
import itertools
from typing import Any, override

from common.exception import SharlyChessException
from common.i18n import _
from data.board import Board
from data.pairings.engines import RoundRobinPairingEngine
from data.pairings.systems import RoundRobinPairingSystem
from data.player import Player
from data.print_documents.options import (
    PlayerSplitPrintOption,
    PrintOption,
    RoundPrintOption,
    PlayerSortPrintOption,
    ShowWarningsPrintOption,
)
from data.tournament import Tournament
from utils import StaticUtils
from utils.enum import Result
from utils.option import OptionHandler, OptionError


class PrintDocument(OptionHandler[PrintOption], ABC):
    def __init__(
        self,
        options: list[PrintOption] | None = None,
        tournament: Tournament | None = None,
    ):
        self.tournament = tournament
        super().__init__(options)

    @property
    @abstractmethod
    def title(self) -> str:
        """Header of the print document."""

    @property
    @abstractmethod
    def template_name(self) -> str:
        """Name of the template representing the printed document.
        Template is intended to be used with a context where
        "document" refers to the PrintDocument object
        """

    @property
    @abstractmethod
    def template_context(self) -> dict[str, Any]:
        """Context to pass to the template *template_name*.
        If multiple classes use the same template, an abstract class per
        template should be defined with the required context, with each
        context variable being a property of this class."""

    @staticmethod
    def validate_for_tournament(tournament: Tournament) -> str | None:
        """Determines if the document is available for *tournament*.
        If it's not, return an explanation message, if it is return None.
        By default, documents are available for all tournaments."""
        return None


class PlayerPrintDocument(PrintDocument, ABC):
    @property
    def template_name(self) -> str:
        return '/admin/print/players.html'

    @property
    @abstractmethod
    def ordered_players(self) -> list[Player]:
        """List of players in the order they should appear in the document."""

    @property
    def ordered_splitted_players(self) -> dict[str, list[Player]]:
        splitter = self._get_option(PlayerSplitPrintOption).player_splitter
        return splitter.split_players(self.ordered_players)

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [PlayerSplitPrintOption]

    @property
    def is_crosstable(self) -> bool:
        return False

    @property
    def is_ranking(self) -> bool:
        return False

    @property
    def is_player_list(self) -> bool:
        return False

    @property
    def is_player_checkin_list(self) -> bool:
        return False

    @property
    def ranking_round(self) -> int | None:
        return None

    @property
    def template_context(self) -> dict[str, Any]:
        # As 'players.html' template is shared with player screens,
        # template context is maintained as is.
        # For future documents, template explicit variables should be
        # favored to document identifying variables
        # ex: show_{var} instead of is_{document}
        return {
            'tournament': self.tournament,
            'players': self.ordered_splitted_players,
            'crosstable': self.is_crosstable,
            'ranking': self.is_ranking,
            'player_list': self.is_player_list,
            'checkin_list': self.is_player_checkin_list,
            'ranking_round': self.ranking_round,
        }


class PlayerListPrintDocument(PlayerPrintDocument):
    @staticmethod
    def static_name() -> str:
        return _('List of players')

    @staticmethod
    def static_id() -> str:
        return 'player-list'

    @property
    def title(self) -> str:
        return _('List of players')

    @property
    def ordered_players(self) -> list[Player]:
        assert self.tournament is not None
        return self.tournament.players_by_name_with_unpaired

    @override
    @property
    def is_player_list(self) -> bool:
        return True


class PlayerCheckinListPrintDocument(PlayerPrintDocument):
    @staticmethod
    def static_name() -> str:
        return _('Players check-in list')

    @staticmethod
    def static_id() -> str:
        return 'player-checkin-list'

    @property
    def title(self) -> str:
        return _('Players check-in list')

    @property
    def ordered_players(self) -> list[Player]:
        assert self.tournament is not None
        return self.tournament.players_by_name_with_unpaired

    @override
    @property
    def is_player_checkin_list(self) -> bool:
        return True


class AbstractPlayerRankingPrintDocument(PlayerPrintDocument, ABC):
    @override
    @property
    def ranking_round(self) -> int:
        assert self.tournament is not None
        return (
            self._get_option(RoundPrintOption).value
            or self.tournament.max_ranking_round
        )

    @property
    def ordered_players(self) -> list[Player]:
        assert self.tournament is not None
        return list(
            self.tournament.compute_player_ranks(
                after_round=self.ranking_round
            ).values()
        )

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [PlayerSplitPrintOption, RoundPrintOption]

    @override
    def validate_options(self):
        super().validate_options()
        ranking_round = self._get_option(RoundPrintOption)
        if ranking_round.value is None:
            return
        assert self.tournament is not None
        if ranking_round.value > self.tournament.rounds:
            raise OptionError(
                _(
                    'This round is not valid (the tournament has {rounds} rounds).'
                ).format(rounds=self.tournament.rounds),
                ranking_round,
            )
        if ranking_round.value > self.tournament.max_ranking_round:
            raise OptionError(
                _('This round is not finished (last finished: #{round}).').format(
                    round=self.tournament.max_ranking_round
                ),
                ranking_round,
            )


class PlayerRankingPrintDocument(AbstractPlayerRankingPrintDocument, ABC):
    @staticmethod
    def static_name() -> str:
        return _('Ranking')

    @staticmethod
    def static_id() -> str:
        return 'ranking'

    @property
    def title(self) -> str:
        if self.ranking_round == 0:
            return _('Ranking before the first round')
        return _('Ranking after round #{round}').format(round=self.ranking_round)

    @override
    @property
    def is_ranking(self) -> bool:
        return True


class PlayerCrosstablePrintDocument(AbstractPlayerRankingPrintDocument, ABC):
    @staticmethod
    def static_name() -> str:
        return _('Crosstable')

    @staticmethod
    def static_id() -> str:
        return 'crosstable'

    @property
    def title(self) -> str:
        if self.ranking_round == 0:
            return _('Crosstable before the first round')
        return _('Crosstable after round #{round}').format(round=self.ranking_round)

    @override
    @property
    def is_crosstable(self) -> bool:
        return True


class PlayerRoundPerformanceIndicatorPrintDocument(PrintDocument):
    @staticmethod
    def static_name() -> str:
        return _('Round performance indicators')

    @staticmethod
    def static_id() -> str:
        return 'round-performance-indicators'

    @property
    def title(self) -> str:
        return _('Performance indicators for round #{round}').format(
            round=self.ranking_round
        )

    @property
    def ranking_round(self) -> int:
        assert self.tournament is not None
        return (
            self._get_option(RoundPrintOption).value
            or self.tournament.max_ranking_round
        )

    @property
    def template_name(self) -> str:
        return '/admin/print/round_performance.html'

    @property
    def ordered_players(self) -> list[tuple[Player, Player, Result, float]]:
        assert self.tournament is not None
        ranking_round = self.ranking_round
        if not ranking_round:
            return []
        results: list[tuple[Player, Player, Result, float]] = []
        for player in self.tournament.players:
            pairing = player.pairings[ranking_round]
            if pairing.opponent_id and pairing.played:
                opponent = self.tournament.players_by_id[pairing.opponent_id]
                expected_score = 1 / (
                    1 + 10 ** ((opponent.rating - player.rating) / 400)
                )
                rating_change = 20 * (pairing.result.points() - expected_score)
                results.append((player, opponent, pairing.result, rating_change))
        return sorted(results, key=lambda p: -p[3])

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [RoundPrintOption]

    @override
    def validate_options(self):
        super().validate_options()
        ranking_round = self._get_option(RoundPrintOption)
        assert self.tournament is not None
        if ranking_round.value is None:
            if self.tournament.max_ranking_round < 1:
                raise OptionError(
                    _('The tournament has not yet started.'),
                    ranking_round,
                )
            return
        if ranking_round.value > self.tournament.rounds:
            raise OptionError(
                _(
                    'This round is not valid (the tournament has {rounds} rounds).'
                ).format(rounds=self.tournament.rounds),
                ranking_round,
            )
        if ranking_round.value > self.tournament.max_ranking_round:
            raise OptionError(
                _('This round is not finished (last finished: #{round}).').format(
                    round=self.tournament.max_ranking_round
                ),
                ranking_round,
            )

    @property
    def template_context(self) -> dict[str, Any]:
        return {
            'tournament': self.tournament,
            'scores': self.ordered_players,
        }


class BoardPrintDocument(PrintDocument, ABC):
    @property
    def template_name(self) -> str:
        return '/admin/print/boards.html'

    @property
    def show_results(self) -> bool:
        return False

    @property
    def boards(self) -> list[Board]:
        assert self.tournament is not None
        for player in self.tournament.players:
            self.tournament.set_player_points(player, before_round=self.at_round)
        return self.tournament.get_round_boards(self.at_round)

    @property
    def template_context(self) -> dict[str, Any]:
        return {
            'show_result': self.show_results,
            'boards': self.boards,
        }

    @property
    def at_round(self) -> int:
        assert self.tournament is not None
        return self._get_option(RoundPrintOption).value or self.tournament.current_round

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [RoundPrintOption]

    @override
    def validate_options(self):
        super().validate_options()
        assert self.tournament is not None
        at_round = self._get_option(RoundPrintOption)
        if at_round.value is None:
            return
        if at_round.value > self.tournament.rounds:
            raise OptionError(
                _(
                    'This round is not valid (the tournament has {rounds} rounds).'
                ).format(rounds=self.tournament.rounds),
                at_round,
            )
        if at_round.value > self.tournament.current_round:
            raise OptionError(
                _(
                    'There is no pairings for this round (last round with pairings: #{round}).'
                ).format(round=self.tournament.current_round),
                at_round,
            )


class PairingPrintDocument(BoardPrintDocument):
    @property
    def title(self) -> str:
        return _('Pairings for round #{round}').format(round=self.at_round)

    @staticmethod
    def static_name() -> str:
        return _('Pairings')

    @staticmethod
    def static_id() -> str:
        return 'pairings'


class ResultPrintDocument(BoardPrintDocument):
    @property
    def title(self) -> str:
        return _('Results for round #{round}').format(round=self.at_round)

    @staticmethod
    def static_name() -> str:
        return _('Results')

    @staticmethod
    def static_id() -> str:
        return 'results'

    @override
    @property
    def show_results(self) -> bool:
        return True


class BergerGridPrintDocument(PrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'berger-grid'

    @staticmethod
    def static_name() -> str:
        return _('Berger grid')

    @property
    def title(self) -> str:
        return self.name

    @property
    def template_name(self) -> str:
        return '/admin/print/berger_grid.html'

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [PlayerSortPrintOption]

    @staticmethod
    def validate_for_tournament(tournament: Tournament) -> str | None:
        if tournament.pairing_system != RoundRobinPairingSystem():
            return _('This document is only available for Round-Robin tournaments.')
        if not tournament.is_fully_paired:
            return _('This document is not available for unpaired tournaments.')
        return None

    @cached_property
    def grid_id_by_player_id(self) -> dict[int, int]:
        assert self.tournament is not None
        player_sorter = self._get_option(PlayerSortPrintOption).player_sorter
        return {
            player.id: index + 1
            for index, player in enumerate(
                player_sorter.sorted_players(self.tournament)
            )
        }

    def grid_results_points(self, results: list[list[Result | None]]) -> str:
        assert self.tournament is not None
        return StaticUtils.points_str(
            sum(
                result.points(self.tournament.point_values)
                for result in itertools.chain.from_iterable(results)
                if result is not None
            )
        )

    def build_result_grid(self) -> dict[int, list[list[Result | None]]]:
        """Build the player results in a grid format ordered by berger numbers.
        Such a grid is returned per player encounter."""

        assert self.tournament is not None
        pairing_engine = self.tournament.pairing_variation.engine
        assert isinstance(pairing_engine, RoundRobinPairingEngine)
        result_grid: dict[int, list[list[Result | None]]] = {
            player.id: [
                [None] * pairing_engine.player_encounters
                for __ in range(self.tournament.player_count)
            ]
            for player in sorted(
                self.tournament.players,
                key=lambda p: self.grid_id_by_player_id[p.id],
            )
        }
        for player in self.tournament.players:
            for pairing in player.pairings.values():
                if not pairing.opponent_id:
                    continue
                opponent_grid_id = self.grid_id_by_player_id[pairing.opponent_id]
                if not self._set_encounter_result(
                    player.id,
                    opponent_grid_id,
                    pairing.result,
                    result_grid,
                ):
                    opponent = self.tournament.players_by_id[pairing.opponent_id]
                    raise SharlyChessException(
                        f'More than {len(result_grid[player.id][opponent_grid_id - 1])} encounters between '
                        f'players {player.full_name} and {opponent.full_name}.'
                    )
        return result_grid

    @staticmethod
    def _set_encounter_result(
        player_id: int,
        opponent_grid_id: int,
        result: Result,
        result_grid: dict[int, list[list[Result | None]]],
    ) -> bool:
        for round_, round_result in enumerate(
            result_grid[player_id][opponent_grid_id - 1]
        ):
            if round_result is None:
                result_grid[player_id][opponent_grid_id - 1][round_] = result
                return True
        return False

    @property
    def template_context(self) -> dict[str, Any]:
        return {
            'result_grid': self.build_result_grid(),
            'grid_id_by_player_id': self.grid_id_by_player_id,
        }


class PrizeListPrintDocument(PrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'prize-list'

    @staticmethod
    def static_name() -> str:
        return _('Prize list')

    @property
    def title(self) -> str:
        return self.name

    @property
    def template_name(self) -> str:
        return '/admin/print/prize_list.html'

    @property
    def template_context(self) -> dict[str, Any]:
        assert self.tournament is not None

        prize_currency = self.tournament.event.prize_currency
        return {
            'ordinal_integer': StaticUtils.ordinal_integer,
            'prize_currency': prize_currency,
            'format_prize_value': partial(
                StaticUtils.currency_value_str,
                currency=prize_currency,
            ),
        }


class PrizeAssignmentPrintDocument(PrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'prize-assignment'

    @staticmethod
    def static_name() -> str:
        return _('Prize assignment')

    @property
    def title(self) -> str:
        assert self.tournament is not None
        after_round = self.tournament.max_ranking_round
        if after_round == self.tournament.rounds:
            return self.name
        if after_round == 0:
            return _('Prize assignment before the first round')
        return _('Prize assignment after round #{round}').format(round=after_round)

    @property
    def template_name(self) -> str:
        return '/admin/print/prize_assignment.html'

    @property
    def template_context(self) -> dict[str, Any]:
        assert self.tournament is not None

        prize_currency = self.tournament.event.prize_currency
        return {
            'show_warnings': self.get_option_values()[0],
            'ordinal_integer': StaticUtils.ordinal_integer,
            'prize_currency': prize_currency,
            'format_prize_value': partial(
                StaticUtils.currency_value_str,
                currency=prize_currency,
            ),
        }

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [ShowWarningsPrintOption]
