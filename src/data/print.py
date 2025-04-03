from abc import ABC, abstractmethod
from collections import defaultdict
from functools import partial, cached_property
from types import UnionType
from typing import Any, Iterable, override

from common.i18n import _
from data.board import Board
from data.player import Player
from data.tournament import Tournament
from data.util import (
    AbstractEntityManager,
    AbstractOptionHandler,
    AbstractOption,
    IdentifiableEntity,
    OptionError,
    PlayerCategory,
    StaticUtils,
)
from plugins.manager import plugin_manager

DOCUMENT_CLASSES: list[type['AbstractPrintDocument']] = []
OPTION_CLASSES: list[type['AbstractOption']] = []
PLAYER_SPLITTER_CLASSES: list[type['AbstractPlayerSplitter']] = []


register_document = partial(StaticUtils.register_class, register=DOCUMENT_CLASSES)
register_option = partial(StaticUtils.register_class, register=OPTION_CLASSES)
register_player_splitter = partial(
    StaticUtils.register_class, register=PLAYER_SPLITTER_CLASSES
)


class PrintDocumentOptionManager(AbstractEntityManager[AbstractOption]):
    @staticmethod
    def entity_types() -> list[type[AbstractOption]]:
        return OPTION_CLASSES


class AbstractPrintDocument(AbstractOptionHandler, ABC):
    def __init__(
        self,
        options: list[AbstractOption] | None = None,
        tournament: Tournament | None = None,
    ):
        self.tournament = tournament
        super().__init__(options)

    @property
    @abstractmethod
    def title(self) -> str:
        pass

    @property
    @abstractmethod
    def template_name(self) -> str:
        """Name of the template representing the printed document.
        Template is intended to be used with a context where
        "document" refers to the AbstractPrintDocument object
        """
        pass

    @property
    @abstractmethod
    def template_context(self) -> dict[str, Any]:
        """Context to pass to the template *template_name*.
        If multiple classes use the same template, an abstract class per
        template should be defined with the required context, with each
        context variable being a property of this class."""
        pass


class PrintDocumentManager(AbstractEntityManager[AbstractPrintDocument]):
    @staticmethod
    def entity_types() -> list[type[AbstractPrintDocument]]:
        return DOCUMENT_CLASSES


class AbstractPlayerSplitter(IdentifiableEntity, ABC):
    @staticmethod
    @abstractmethod
    def get_split_key(player: Player) -> str:
        """Extract the split key from a player.
        Players will be grouped by sort key."""
        pass

    @staticmethod
    def sorted_split_keys(split_keys: Iterable[str]) -> list[str]:
        """Returns the split keys ordered. Defaults to alphabetical sort."""
        return sorted(split_keys)

    def split_players(self, players: list[Player]) -> dict[str, list[Player]]:
        splitted_players = defaultdict(list)
        for player in players:
            splitted_players[self.get_split_key(player)].append(player)
        return {
            key: splitted_players[key]
            for key in self.sorted_split_keys(splitted_players.keys())
        }


class PrintPlayerSplitterManager(AbstractEntityManager[AbstractPlayerSplitter]):
    @staticmethod
    def entity_types() -> list[type[AbstractPlayerSplitter]]:
        splitters = PLAYER_SPLITTER_CLASSES
        plugin_manager.hook.insert_print_player_splitter_types(
            player_splitter_types=splitters
        )
        return splitters


@register_option
class RoundPrintOption(AbstractOption):
    @staticmethod
    def static_id() -> str:
        return 'round'

    @property
    def type(self) -> type | UnionType:
        return int | None

    @property
    def default_value(self) -> Any:
        return None

    @property
    def template_name(self) -> str:
        return '/admin/event/print_options/round.html'

    @override
    def validate(self):
        super().validate()
        if self.value is not None and self.value < 1:
            raise OptionError(_('A positive integer is expected.'), self)


@register_option
class PlayerPrintSplitOption(AbstractOption):
    @staticmethod
    def static_id() -> str:
        return 'player-split'

    @property
    def type(self) -> type | UnionType:
        return str

    @property
    def default_value(self) -> Any:
        return 'no-split'

    @property
    def template_name(self) -> str:
        return '/admin/event/print_options/player_split.html'

    @property
    def player_splitter_options(self) -> dict[str, str]:
        return PrintPlayerSplitterManager.options()

    @cached_property
    def player_splitter(self) -> AbstractPlayerSplitter | None:
        return PrintPlayerSplitterManager.get_object(self.value)

    @override
    def validate(self):
        try:
            _splitter = self.player_splitter
        except KeyError:
            # Untranslated, should not happen
            raise OptionError(f'Unknown player splitter: {self.value}', self)


@register_player_splitter
class NoSplitPlayerSplitter(AbstractPlayerSplitter):
    @staticmethod
    def static_id() -> str:
        return 'no-split'

    @staticmethod
    def static_name() -> str:
        return '-'

    @staticmethod
    def get_split_key(player: Player) -> str:
        return ''


@register_player_splitter
class CategoryPlayerSplitter(AbstractPlayerSplitter):
    @staticmethod
    def static_id() -> str:
        return 'category'

    @staticmethod
    def static_name() -> str:
        return _('Category')

    @staticmethod
    def get_split_key(player: Player) -> str:
        return player.category.short_name

    @staticmethod
    def sorted_split_keys(split_keys: Iterable[str]) -> list[str]:
        ordered_keys = [category.short_name for category in PlayerCategory]
        return sorted(split_keys, key=lambda key: ordered_keys.index(key))


@register_player_splitter
class ClubPlayerSplitter(AbstractPlayerSplitter):
    @staticmethod
    def static_id() -> str:
        return 'club'

    @staticmethod
    def static_name() -> str:
        return _('Club')

    @staticmethod
    def get_split_key(player: Player) -> str:
        return player.club.name if player.club else ''


@register_player_splitter
class FederationPlayerSplitter(AbstractPlayerSplitter):
    @staticmethod
    def static_id() -> str:
        return 'federation'

    @staticmethod
    def static_name() -> str:
        return _('Federation')

    @staticmethod
    def get_split_key(player: Player) -> str:
        return player.federation.name


class AbstractPlayerPrintDocument(AbstractPrintDocument, ABC):
    @property
    def template_name(self) -> str:
        return '/admin/print/players.html'

    @property
    @abstractmethod
    def ordered_players(self) -> list[Player]:
        pass

    @property
    def ordered_splitted_players(self) -> dict[str, list[Player]]:
        split_by = self._get_option(PlayerPrintSplitOption).value
        splitter: AbstractPlayerSplitter = PrintPlayerSplitterManager.get_object(
            split_by
        )
        return splitter.split_players(self.ordered_players)

    @staticmethod
    def available_options() -> list[type[AbstractOption]]:
        return [PlayerPrintSplitOption]

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
            'ranking_round': self.ranking_round,
        }


@register_document
class PlayerListPrintDocument(AbstractPlayerPrintDocument):
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


class AbstractPlayerRankingPrintDocument(AbstractPlayerPrintDocument, ABC):
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
    def available_options() -> list[type[AbstractOption]]:
        return [PlayerPrintSplitOption, RoundPrintOption]

    @override
    def validate_options(self):
        super().validate_options()
        ranking_round = self._get_option(RoundPrintOption).value
        if ranking_round is None:
            return
        assert self.tournament is not None
        if ranking_round > self.tournament.rounds:
            raise OptionError(
                _('Not part of the selected tournament ({rounds} rounds).').format(
                    rounds=self.tournament.rounds
                ),
                ranking_round,
            )
        if ranking_round > self.tournament.max_ranking_round:
            raise OptionError(
                _('Round not finished (last finished: {round}).').format(
                    round=self.tournament.max_ranking_round
                ),
                ranking_round,
            )


@register_document
class PlayerRankingPrintDocument(AbstractPlayerRankingPrintDocument, ABC):
    @staticmethod
    def static_name() -> str:
        return _('Ranking')

    @staticmethod
    def static_id() -> str:
        return 'ranking'

    @property
    def title(self) -> str:
        return _('Ranking after round #{round}').format(round=self.ranking_round)

    @override
    @property
    def is_ranking(self) -> bool:
        return True


@register_document
class PlayerCrosstablePrintDocument(AbstractPlayerRankingPrintDocument, ABC):
    @staticmethod
    def static_name() -> str:
        return _('Crosstable')

    @staticmethod
    def static_id() -> str:
        return 'crosstable'

    @property
    def title(self) -> str:
        return _('Crosstable after round #{round}').format(round=self.ranking_round)

    @override
    @property
    def is_crosstable(self) -> bool:
        return True


class AbstractBoardPrintDocument(AbstractPrintDocument, ABC):
    @property
    def template_name(self) -> str:
        return '/admin/print/boards.html'

    @property
    def show_results(self) -> bool:
        return False

    @property
    def boards(self) -> list[Board]:
        assert self.tournament is not None
        self.tournament.calculate_points_before_round(before_round=self.at_round)
        boards, _ = self.tournament.build_boards(self.at_round)
        return boards

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
    def available_options() -> list[type[AbstractOption]]:
        return [RoundPrintOption]

    @override
    def validate_options(self):
        super().validate_options()
        assert self.tournament is not None
        at_round = self._get_option(RoundPrintOption).value
        if at_round is None:
            return
        if at_round > self.tournament.rounds:
            raise OptionError(
                _('Not part of the selected tournament ({rounds} rounds).').format(
                    rounds=self.tournament.rounds
                ),
                at_round,
            )
        if at_round > self.tournament.current_round:
            raise OptionError(
                _('Round not paired (last paired: {round}).').format(
                    round=self.tournament.current_round
                ),
                at_round,
            )


@register_document(index=1)
class PairingPrintDocument(AbstractBoardPrintDocument):
    @property
    def title(self) -> str:
        return _('Pairings for round #{round}').format(round=self.at_round)

    @staticmethod
    def static_name() -> str:
        return _('Pairings')

    @staticmethod
    def static_id() -> str:
        return 'pairings'


@register_document(index=2)
class ResultPrintDocument(AbstractBoardPrintDocument):
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
