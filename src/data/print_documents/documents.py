from abc import ABC, abstractmethod
from functools import cached_property, partial
import itertools
from typing import Any, Callable, override
from collections import Counter

from common import format_timestamp
from common.exception import SharlyChessException, OptionError
from common.i18n import _, ngettext
from common.i18n.utils import unicode_normalize
from data.board import Board
from data.pairings.engines import RoundRobinPairingEngine
from data.pairings.systems import RoundRobinPairingSystem, SwissPairingSystem
from data.player import Player, PlayerTitle, dataclass, plugin_manager
from data.event import Event
from data.print_documents.options import (
    PairingStylePrintOption,
    PlayerPrintOption,
    PlayerSplitPrintOption,
    PrintOption,
    QRCodeNetworkPrintOption,
    QRCodePrintOption,
    RoundPrintOption,
    PlayerSortPrintOption,
    ShowWarningsPrintOption,
    ClubThresholdPrintOption,
    TournamentPrintOption,
    TournamentsPrintOption,
)
from data.tournament import Tournament
from utils import StaticUtils
from utils.enum import Result
from utils.option import Option, OptionHandler


class PrintDocument(OptionHandler[PrintOption], ABC):
    def __init__(
        self,
        event: Event | None = None,
        options: list[PrintOption] | None = None,
    ):
        self.event = event
        super().__init__(options)

    @override
    def default_options(self) -> list[PrintOption]:
        return [option_type(self.event) for option_type in self.available_options()]

    @override
    def _get_option[V: Option](self, option_type: type[V]) -> V:
        return next(
            (option for option in self.options if isinstance(option, option_type)),
            option_type(self.event),
        )

    @property
    def tournament(self) -> Tournament:
        """The tournament for which the document is printed."""
        assert self.event is not None
        tournament_id = self._get_option(TournamentPrintOption).value
        if tournament_id:
            return self.event.tournaments_by_id[tournament_id]
        return self.tournaments[0]

    @property
    def tournaments(self) -> list[Tournament]:
        """The tournaments for which the document is printed."""
        assert self.event is not None
        tournament_ids = self._get_option(TournamentsPrintOption).value
        if not tournament_ids:
            return list(self.event.tournaments)
        return [
            self.event.tournaments_by_id[int(tournament_id)]
            for tournament_id in tournament_ids.split(',')
        ]

    @property
    def subtitle(self) -> str:
        """Subtitle of the print document."""
        assert self.event is not None
        return (
            self.event.name
            if len(self.tournaments) == len(list(self.event.tournaments))
            else ', '.join(tournament.name for tournament in self.tournaments)
        )

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
    def ordered_split_players(self) -> dict[str, list[Player]]:
        splitter = self._get_option(PlayerSplitPrintOption).player_splitter
        return splitter.split_players(self.ordered_players)

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [TournamentsPrintOption, PlayerSplitPrintOption]

    @property
    def multiple_tournaments(self) -> bool:
        return True

    @property
    def is_crosstable(self) -> bool:
        return False

    @property
    def is_ranking(self) -> bool:
        return False

    @property
    def is_pairings_list(self) -> bool:
        return False

    @property
    def at_round(self) -> int | None:
        return None

    @property
    def is_player_list(self) -> bool:
        return False

    @property
    def is_player_checkin_list(self) -> bool:
        return False

    @property
    def ranking_round(self) -> int | None:
        return None

    @override
    @property
    def subtitle(self) -> str:
        """Subtitle of the print document."""
        return (
            self.tournament.name if not self.multiple_tournaments else super().subtitle
        )

    @property
    def template_context(self) -> dict[str, Any]:
        # As 'players.html' template is shared with player screens,
        # template context is maintained as is.
        # For future documents, template explicit variables should be
        # favored to document identifying variables
        # ex: show_{var} instead of is_{document}
        return {
            'tournament': self.tournament,
            'tournaments': self.tournaments,
            'multiple_tournaments': self.multiple_tournaments
            and len(self.tournaments) > 1,
            'subtitle': self.subtitle,
            'players': self.ordered_split_players,
            'crosstable': self.is_crosstable,
            'ranking': self.is_ranking,
            'player_list': self.is_player_list,
            'pairings_list': self.is_pairings_list,
            'pairings_round': self.at_round,
            'checkin_list': self.is_player_checkin_list,
            'ranking_round': self.ranking_round,
        }


class PlayerListPrintDocument(PlayerPrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'player-list'

    @staticmethod
    def static_name() -> str:
        return _('List of players')

    @property
    def title(self) -> str:
        return _('List of players')

    @property
    def ordered_players(self) -> list[Player]:
        assert self.event is not None
        tournament_ids = [tournament.id for tournament in self.tournaments]
        return [
            player
            for player in self.event.players_sorted_by_name
            if player.tournament.id in tournament_ids
        ]

    @override
    @property
    def is_player_list(self) -> bool:
        return True


class PlayerCheckinListPrintDocument(PlayerPrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'player-checkin-list'

    @staticmethod
    def static_name() -> str:
        return _('Players check-in list')

    @property
    def title(self) -> str:
        return _('Players check-in list')

    @property
    def ordered_players(self) -> list[Player]:
        assert self.event is not None
        tournament_ids = [tournament.id for tournament in self.tournaments]
        return [
            player
            for player in self.event.players_sorted_by_name
            if player.tournament.id in tournament_ids
        ]

    @override
    @property
    def is_player_checkin_list(self) -> bool:
        return True


class AbstractPlayerRankingPrintDocument(PlayerPrintDocument, ABC):
    @override
    @property
    def ranking_round(self) -> int:
        return (
            self._get_option(RoundPrintOption).value
            or self.tournament.max_ranking_round
        )

    @property
    def ordered_players(self) -> list[Player]:
        return list(
            self.tournament.compute_player_ranks(
                after_round=self.ranking_round
            ).values()
        )

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [TournamentPrintOption, PlayerSplitPrintOption, RoundPrintOption]

    @override
    @property
    def multiple_tournaments(self) -> bool:
        return False

    @override
    def validate_options(self):
        super().validate_options()
        ranking_round = self._get_option(RoundPrintOption)
        if ranking_round.value is None:
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


class PlayerRankingPrintDocument(AbstractPlayerRankingPrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'ranking'

    @staticmethod
    def static_name() -> str:
        return _('Ranking')

    @property
    def title(self) -> str:
        if self.ranking_round == 0:
            return _('Ranking before the first round')
        return _('Ranking after round #{round}').format(round=self.ranking_round)

    @override
    @property
    def is_ranking(self) -> bool:
        return True


class PlayerCrosstablePrintDocument(AbstractPlayerRankingPrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'crosstable'

    @staticmethod
    def static_name() -> str:
        return _('Crosstable')

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
    def static_id() -> str:
        return 'round-performance-indicators'

    @staticmethod
    def static_name() -> str:
        return _('Round performance indicators')

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [TournamentPrintOption, RoundPrintOption]

    @property
    def title(self) -> str:
        return _('Performance indicators for round #{round}').format(
            round=self.ranking_round
        )

    @property
    def ranking_round(self) -> int:
        return (
            self._get_option(RoundPrintOption).value
            or self.tournament.max_ranking_round
        )

    @property
    def template_name(self) -> str:
        return '/admin/print/round_performance.html'

    @property
    def ordered_players(self) -> list[tuple[Player, Player, Result, float]]:
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

    @override
    def validate_options(self):
        super().validate_options()
        ranking_round = self._get_option(RoundPrintOption)
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
            'subtitle': self.tournament.name,
            'scores': self.ordered_players,
        }


class BoardPrintDocument(PrintDocument, ABC):
    @property
    def template_name(self) -> str:
        return '/admin/print/boards.html'

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [TournamentPrintOption, RoundPrintOption]

    @property
    def show_results(self) -> bool:
        return False

    @property
    def boards(self) -> list[Board]:
        assert self.event is not None
        self.tournament.set_for_round(self.at_round)
        return self.tournament.get_round_boards(self.at_round)

    @property
    def template_context(self) -> dict[str, Any]:
        return {
            'tournament': self.tournament,
            'subtitle': self.tournament.name,
            'show_result': self.show_results,
            'boards': self.boards,
            'selected_round': self.at_round,
        }

    @property
    def at_round(self) -> int:
        return self._get_option(RoundPrintOption).value or self.tournament.current_round

    @override
    def validate_options(self):
        super().validate_options()
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


class PairingPrintDocument(PrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'pairings'

    @staticmethod
    def static_name() -> str:
        return _('Pairings')

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [TournamentPrintOption, PairingStylePrintOption, RoundPrintOption]

    @cached_property
    def sub_document(self) -> PrintDocument:
        return self._get_option(
            PairingStylePrintOption
        ).pairing_style.print_document_type(event=self.event, options=self.options)

    @property
    def title(self) -> str:
        return self.sub_document.title

    @property
    def template_name(self) -> str:
        return self.sub_document.template_name

    @property
    def template_context(self) -> dict[str, Any]:
        return self.sub_document.template_context


class BoardPairingPrintDocument(BoardPrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'board-pairings'

    @staticmethod
    def static_name() -> str:
        return _('Board Pairings')

    @property
    def title(self) -> str:
        return _('Pairings for round #{round}').format(round=self.at_round)


class PlayerPairingPrintDocument(PlayerPrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'player-pairings'

    @staticmethod
    def static_name() -> str:
        return _('Player pairings')

    @property
    def title(self) -> str:
        return _('Pairings for round #{round}').format(round=self.at_round)

    @property
    def at_round(self) -> int:
        return self._get_option(RoundPrintOption).value or self.tournament.current_round

    @override
    @property
    def multiple_tournaments(self) -> bool:
        return False

    @override
    @property
    def ordered_players(self) -> list[Player]:
        self.tournament.set_for_round(self.at_round)
        return self.tournament.players_by_name_without_unpaired

    @override
    @property
    def is_pairings_list(self) -> bool:
        return True


class ResultPrintDocument(BoardPrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'results'

    @staticmethod
    def static_name() -> str:
        return _('Results')

    @property
    def title(self) -> str:
        return _('Results for round #{round}').format(round=self.at_round)

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [TournamentPrintOption]

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

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [TournamentPrintOption, PlayerSortPrintOption]

    @property
    def title(self) -> str:
        return self.name

    @property
    def template_name(self) -> str:
        return '/admin/print/berger_grid.html'

    @staticmethod
    def validate_for_tournament(tournament: Tournament) -> str | None:
        if tournament.pairing_system != RoundRobinPairingSystem():
            return _('This document is only available for Round-Robin tournaments.')
        if not tournament.is_fully_paired:
            return _('This document is not available for unpaired tournaments.')
        return None

    @cached_property
    def grid_id_by_player_id(self) -> dict[int, int]:
        player_sorter = self._get_option(PlayerSortPrintOption).player_sorter
        return {
            player.id: index + 1
            for index, player in enumerate(
                player_sorter.sorted_players(self.tournament)
            )
        }

    def grid_results_points(self, results: list[list[Result | None]]) -> str:
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
        self.tournament.compute_player_ranks()
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

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [TournamentsPrintOption]

    @property
    def title(self) -> str:
        return self.name

    @property
    def template_name(self) -> str:
        return '/admin/print/prize_list.html'

    @property
    def template_context(self) -> dict[str, Any]:
        assert self.event is not None
        prize_currency = self.event.prize_currency
        return {
            'tournaments': self.tournaments,
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

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [TournamentsPrintOption, ShowWarningsPrintOption]

    @property
    def title(self) -> str:
        return _('Prize assignment')

    @property
    def template_name(self) -> str:
        return '/admin/print/prize_assignment.html'

    @property
    def template_context(self) -> dict[str, Any]:
        assert self.event is not None
        prize_currency = self.event.prize_currency
        return {
            'tournaments': self.tournaments,
            'show_warnings': self.get_option_values()[0],
            'ordinal_integer': StaticUtils.ordinal_integer,
            'prize_currency': prize_currency,
            'format_prize_value': partial(
                StaticUtils.currency_value_str,
                currency=prize_currency,
            ),
        }


@dataclass
class StatisticsSection:
    title: str
    rows: dict[str, int]
    subtitle: str | None = None


class StatisticsPrintDocument(PrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'statistics'

    @staticmethod
    def static_name() -> str:
        return _('Statistics')

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [TournamentsPrintOption, ClubThresholdPrintOption]

    @property
    def title(self) -> str:
        return _('Participation Statistics')

    @property
    def template_name(self) -> str:
        return '/admin/print/statistics.html'

    def stat_section(
        self,
        attr_name: str,
        title: str,
        *,
        sort_key: Callable[[tuple[Any, int]], Any] | None = None,
        label_getter: Callable[[Any], Any] = lambda x: x.name
        if hasattr(x, 'name')
        else x,
        min_count: int | None = None,
        filter_func: Callable[[Any], bool] | None = None,
        subtitle_fn: Callable[[int], str] | None = None,
    ) -> StatisticsSection | None:
        values = [
            value
            for tournament in self.tournaments
            for p in tournament.players
            if (value := getattr(p, attr_name)) is not None
            and (filter_func(value) if filter_func else True)
        ]

        full_counter = Counter(values)

        if not full_counter:
            return None

        items: list[tuple[Any, int]] = list(full_counter.items())
        if min_count is not None:
            items = [(k, v) for k, v in items if v >= min_count]

        if sort_key:
            items = sorted(items, key=sort_key)

        subtitle = subtitle_fn(len(full_counter)) if subtitle_fn else None

        return StatisticsSection(
            title=title,
            rows={label_getter(k): v for k, v in items},
            subtitle=subtitle,
        )

    def rating_range_section(self) -> StatisticsSection | None:
        all_players = [p for t in self.tournaments for p in t.players]

        ratings = [p.rating for p in all_players if not p.estimated]
        estimated_count = sum(1 for p in all_players if p.estimated)

        if not ratings and not estimated_count:
            return None

        max_rating = max(ratings, default=0)
        buckets = [(0, 1000)]
        r = 1001
        while r <= max_rating:
            buckets.append((r, r + 199))
            r += 200

        # Count players per bucket
        counter: Counter[tuple[int, int]] = Counter()
        for p in all_players:
            if p.estimated:
                continue
            for start, end in buckets:
                if start <= p.rating <= end:
                    counter[(start, end)] += 1
                    break

        rows: dict[str, int] = {
            _('{start} → {end}').format(start=start, end=end): counter[(start, end)]
            for (start, end) in reversed(buckets)
            if counter[(start, end)] > 0
        }

        if estimated_count:
            rows[_('Unrated *** PLURAL')] = estimated_count

        non_estimated_players = [
            player
            for tournament in self.tournaments
            for player in tournament.players
            if not player.estimated
        ]
        average_rating = (
            round(
                sum(player.rating for player in non_estimated_players)
                / len(non_estimated_players)
            )
            if non_estimated_players
            else None
        )

        return StatisticsSection(
            title=_('Rating ranges'),
            rows=rows,
            subtitle=_('Average rating: {rating}').format(rating=average_rating),
        )

    @property
    def template_context(self) -> dict[str, Any]:
        club_threshold = self._get_option(ClubThresholdPrintOption).value or 0

        statistics: list[StatisticsSection] = []

        per_plugin_sections = plugin_manager.hook_for_event(
            self.event, 'get_extra_statistics_sections'
        )(document=self, tournaments=self.tournaments)

        for attr_name, title, sort_key, min_count, filter_func, subtitle_fn in [
            (
                'tournament',
                _('Tournaments'),
                lambda item: item[0].name,
                None,
                lambda x: x is not None,
                None,
            ),
            (
                'title',
                _('Titled players'),
                lambda item: -item[0].value,
                None,
                lambda x: x != PlayerTitle.NONE,
                None,
            ),
            (
                'rating_type',
                _('Rating types'),
                lambda item: -item[0].value,
                None,
                None,
                None,
            ),
            (
                'category',
                _('Age categories'),
                lambda item: -item[0].value,
                None,
                None,
                None,
            ),
            ('gender', _('Genders'), lambda item: item[0].value, None, None, None),
            (
                'federation',
                _('Federations'),
                lambda item: (-item[1], item[0].name),
                None,
                None,
                lambda count: ngettext(
                    '{count} federation represented',
                    '{count} federations represented',
                    count,
                ).format(count=count),
            ),
            (
                'club',
                _('Clubs'),
                lambda item: (
                    -item[1],
                    unicode_normalize(
                        item[0].name.lower().translate(str.maketrans('', '', '"\''))
                    ),
                ),
                club_threshold,
                lambda item: item.name != '',
                lambda count: ngettext(
                    '{count} club represented', '{count} clubs represented', count
                ).format(count=count),
            ),
        ]:
            if attr_name == 'tournament' and len(self.tournaments) <= 1:
                continue  # Skip if there's only one tournament

            for sections in per_plugin_sections:
                for section in sections:
                    if section.at == attr_name:
                        statistics.append(section)

            section = self.stat_section(
                attr_name,
                title,
                sort_key=sort_key,
                min_count=min_count,
                filter_func=filter_func,
                subtitle_fn=subtitle_fn,
            )

            if section:
                statistics.append(section)

            if attr_name == 'rating_type':
                section = self.rating_range_section()
                if section:
                    statistics.append(section)

        return {
            'tournaments': self.tournaments,
            'subtitle': self.subtitle,
            'statistics': statistics,
        }


class NormReportPrintDocument(PrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'norm_report'

    @staticmethod
    def static_name() -> str:
        return _('Norm Report')

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [TournamentPrintOption, PlayerPrintOption]

    @property
    def title(self) -> str:
        return 'Certificate of Title Results'

    @property
    def template_name(self) -> str:
        return '/admin/print/norm_report.html'

    @property
    def template_context(self) -> dict[str, Any]:
        player_id = self._get_option(PlayerPrintOption).value
        player = self.tournament.players_by_id[player_id]
        norms = {
            norm_title: norm
            for norm_title, norm in player.achieves_any_title_norm().items()
            if norm.meets_gender
        }
        return {
            'event': self.event,
            'tournament': self.tournament,
            'is_swiss': self.tournament.pairing_system == SwissPairingSystem(),
            'start': format_timestamp(self.tournament.start_timestamp, '%Y.%m.%d'),
            'end': format_timestamp(self.tournament.stop_timestamp, '%Y.%m.%d'),
            'norms': norms,
            'player': player,
        }


class QRCodePrintDocument(PrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'qrcode'

    @staticmethod
    def static_name() -> str:
        return _('QR Code')

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [QRCodePrintOption, TournamentPrintOption, QRCodeNetworkPrintOption]

    @property
    def title(self) -> str:
        qrcode_type = self._get_option(QRCodePrintOption).qrcode_type
        return qrcode_type.title(self)

    @property
    def template_name(self) -> str:
        return '/admin/print/qrcode.html'

    @property
    def template_context(self) -> dict[str, Any]:
        qrcode_type = self._get_option(QRCodePrintOption).qrcode_type

        success, result = qrcode_type.url(self)
        qrcode_base64 = qrcode_type.get_qr_code(result) if success else None

        return {
            'qrcode_type': qrcode_type,
            'subtitle': qrcode_type.subtitle(self),
            'info': qrcode_type.info(self),
            'error_message': result if not success else None,
            'qrcode_url': result if success else None,
            'qrcode_base64': qrcode_base64,
        }
