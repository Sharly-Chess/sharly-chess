import itertools
from abc import ABC, abstractmethod
from collections import defaultdict
from functools import partial, cached_property
from types import UnionType
from typing import Any, Iterable, override

from common.i18n import _
from data.player import Player
from data.tournament import Tournament
from data.util import AbstractOptionHandler, AbstractOption, StaticUtils, PlayerCategory, OptionError
from plugins.manager import plugin_manager

DOCUMENT_CLASSES: list[type['AbstractPrintDocument']] = []
OPTION_CLASSES: list[type['AbstractOption']] = []
PLAYER_SPLITTER_CLASSES: list[type['AbstractPlayerSplitter']] = []


register_document = partial(
    StaticUtils.register_class, register=DOCUMENT_CLASSES
)
register_option = partial(StaticUtils.register_class, register=OPTION_CLASSES)
register_player_splitter = partial(
    StaticUtils.register_class, register=PLAYER_SPLITTER_CLASSES
)


class PrintDocumentManager:
    @staticmethod
    def document_types() -> list[type['AbstractPrintDocument']]:
        return DOCUMENT_CLASSES

    @classmethod
    def default_documents(cls) -> list['AbstractPrintDocument']:
        return [type_()  for type_ in cls.document_types()]

    @classmethod
    def document_type_by_id(cls) -> dict[str, type['AbstractPrintDocument']]:
        return {type_().id: type_ for type_ in cls.document_types()}

    @staticmethod
    def option_types() -> list[type['AbstractOption']]:
        return OPTION_CLASSES

    @classmethod
    def default_options(cls) -> list['AbstractOption']:
        return [type_()  for type_ in cls.option_types()]

    @classmethod
    def option_type_by_id(cls) -> dict[str, type['AbstractOption']]:
        return {type_().id: type_ for type_ in cls.option_types()}

    @staticmethod
    def player_splitters() -> list['AbstractPlayerSplitter']:
        splitters = [type_() for type_ in PLAYER_SPLITTER_CLASSES]
        plugin_manager.hook.insert_print_player_splitters(
            player_splitters=splitters
        )
        return splitters

    @classmethod
    def player_splitter_by_id(cls) -> dict[str, 'AbstractPlayerSplitter']:
        return {splitter.id: splitter for splitter in cls.player_splitters()}


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


class AbstractPlayerSplitter(ABC):
    @property
    @abstractmethod
    def id(self) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

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


@register_option
class RoundPrintOption(AbstractOption):
    @property
    def id(self) -> str:
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
    @property
    def id(self) -> str:
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
        return {
            splitter.id: splitter.name
            for splitter in PrintDocumentManager.player_splitters()
        }

    @cached_property
    def player_splitter(self) -> AbstractPlayerSplitter | None:
        return PrintDocumentManager.player_splitter_by_id().get(
            self.value
        )

    @override
    def validate(self):
        if not self.player_splitter:
            # Untranslated, should not happen
            raise OptionError(f'Unknown player splitter: {self.value}', self)


@register_player_splitter
class NoSplitPlayerSplitter(AbstractPlayerSplitter):
    @property
    def id(self) -> str:
        return 'no-split'

    @property
    def name(self) -> str:
        return '-'

    @staticmethod
    def get_split_key(player: Player) -> str:
        return ''


@register_player_splitter
class CategoryPlayerSplitter(AbstractPlayerSplitter):
    @property
    def id(self) -> str:
        return 'category'

    @property
    def name(self) -> str:
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
    @property
    def id(self) -> str:
        return 'club'

    @property
    def name(self) -> str:
        return _('Club')

    @staticmethod
    def get_split_key(player: Player) -> str:
        return player.club.name


@register_player_splitter
class FederationPlayerSplitter(AbstractPlayerSplitter):
    @property
    def id(self) -> str:
        return 'federation'

    @property
    def name(self) -> str:
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
        splitter: AbstractPlayerSplitter = (
            PrintDocumentManager.player_splitter_by_id()[split_by]
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
            'title': self.title,
            'crosstable': self.is_crosstable,
            'ranking': self.is_ranking,
            'player_list': self.is_player_list,
            'ranking_round': self.ranking_round,
        }


@register_document
class PlayerListPrintDocument(AbstractPlayerPrintDocument):
    @property
    def name(self) -> str:
        return _('List of players')

    @property
    def id(self) -> str:
        return 'player-list'

    @property
    def title(self) -> str:
        return _('List of players')

    @property
    def ordered_players(self) -> list[Player]:
        return self.tournament.players_by_name_with_unpaired

    @override
    @property
    def is_player_list(self) -> bool:
        return True


class AbstractPlayerRankingPrintDocument(AbstractPlayerPrintDocument, ABC):
    @override
    @property
    def ranking_round(self) -> int:
        return (
            self._get_option(RoundPrintOption).value or
            self.tournament.max_ranking_round
        )

    @property
    def ordered_players(self) -> list[Player]:
        return list(self.tournament.compute_player_ranks(
            after_round=self.ranking_round
        ).values())

    @staticmethod
    def available_options() -> list[type[AbstractOption]]:
        return [PlayerPrintSplitOption, RoundPrintOption]

    @override
    def validate_options(self):
        super().validate_options()
        ranking_round = self._get_option(RoundPrintOption).value
        if ranking_round is None:
            return
        if ranking_round > self.tournament.rounds:
            raise OptionError(
                _(
                    'Not part of the selected tournament ({rounds} rounds).'
                ).format(rounds=self.tournament.rounds),
                ranking_round,
            )
        if ranking_round > self.tournament.max_ranking_round:
            raise OptionError(
                _(
                    'Round not finished (last finished: {round}).'
                ).format(round=self.tournament.max_ranking_round),
                ranking_round,
            )


@register_document
class PlayerRankingPrintDocument(AbstractPlayerRankingPrintDocument, ABC):
    @property
    def name(self) -> str:
        return _('Ranking')

    @property
    def id(self) -> str:
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
    @property
    def name(self) -> str:
        return _('Crosstable')

    @property
    def id(self) -> str:
        return 'crosstable'

    @property
    def title(self) -> str:
        return _('Crosstable after round #{round}').format(round=self.ranking_round)

    @override
    @property
    def is_crosstable(self) -> bool:
        return True