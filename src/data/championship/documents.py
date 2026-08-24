"""Printable Championship documents.

Championship is not event-bound, so it cannot reuse the event print-document
managers (which are ``Event``-scoped). It does reuse the generic option
substrate: each option is an :class:`Option` carrying its own form fragment and
type — the same contract the event ``PrintOption`` uses, only bound to a
``Championship`` instead of an ``Event``. A document declares the option types
it accepts; the controller assembles the actual page data from the existing
ranking/competitor helpers."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from common.i18n import _
from data.championship.options import ChampionshipCompetitorType
from utils.option import Option

if TYPE_CHECKING:
    from data.championship.championship import Championship


class ChampionshipPrintOption(Option, ABC):
    """An option of a championship print document. Mirrors the event
    ``PrintOption`` but is bound to a ``Championship`` (its value or default may
    depend on the sources) rather than an ``Event``."""

    def __init__(self, championship: 'Championship', value: Any | None = None):
        # Set before super().__init__: default_value may read the championship.
        self.championship = championship
        super().__init__(value)

    @property
    def template_name(self) -> str:
        return f'/admin/championship/print_options/{self.template_file_stem}.html'

    @property
    @abstractmethod
    def template_file_stem(self) -> str:
        """Stem of the option's form fragment."""


class RankingSetsPrintOption(ChampionshipPrintOption):
    """Which rankings to print — the overall ranking and/or specific category
    rankings. An empty value means every set."""

    @staticmethod
    def static_id() -> str:
        return 'sets'

    @staticmethod
    def static_name() -> str:
        return _('Rankings to print')

    @property
    def template_file_stem(self) -> str:
        return 'ranking_sets'

    @property
    def type(self) -> type:
        return list[str]

    @property
    def default_value(self) -> Any:
        return []

    def validate(self):
        self._validate_list_type(str)


class TournamentNamePrintOption(ChampionshipPrintOption):
    """How each source is named in the tournament list: by its event, by its
    tournament, or both."""

    EVENT = 'event'
    TOURNAMENT = 'tournament'
    BOTH = 'both'

    @staticmethod
    def static_id() -> str:
        return 'tournament_name'

    @staticmethod
    def static_name() -> str:
        return _('Naming')

    @property
    def template_file_stem(self) -> str:
        return 'tournament_name'

    @property
    def type(self) -> type:
        return str

    @property
    def default_value(self) -> Any:
        """Auto: the event name when every event contributes a single
        tournament, the tournament name when every source is from one event,
        otherwise both."""
        event_ids = [source.event_uniq_id for source in self.championship.sources]
        distinct_events = set(event_ids)
        if len(distinct_events) <= 1:
            return self.TOURNAMENT
        if len(event_ids) == len(distinct_events):
            return self.EVENT
        return self.BOTH


class IncludePlayerPopoverPrintOption(ChampionshipPrintOption):
    """Whether each competitor's row carries a hover popover with the per-stage
    breakdown (as shown on the standings tab)."""

    @staticmethod
    def static_id() -> str:
        return 'include_popover'

    @staticmethod
    def static_name() -> str:
        return _('Show the stage details on hover')

    @property
    def template_file_stem(self) -> str:
        return 'include_popover'

    @property
    def type(self) -> type:
        return bool

    @property
    def default_value(self) -> Any:
        return False


class ChampionshipPrintDocument(ABC):
    """A printable Championship document: a set of :class:`ChampionshipPrintOption`
    plus the identity the print template reads (``id`` / ``title`` / ``tab_title``)."""

    #: Print template extending ``admin/print/base.html``.
    template_name: str

    def __init__(
        self,
        championship: 'Championship',
        options: list[ChampionshipPrintOption] | None = None,
    ):
        self.championship = championship
        self.options: list[ChampionshipPrintOption] = options or []

    @staticmethod
    @abstractmethod
    def static_id() -> str:
        """Stable id used in the document URL and the picker."""

    @staticmethod
    @abstractmethod
    def label(championship: 'Championship') -> str:
        """Translated name for the picker (may depend on individual vs team)."""

    @staticmethod
    def available_options() -> list[type[ChampionshipPrintOption]]:
        """Option types this document accepts, in display order."""
        return []

    def default_options(self) -> list[ChampionshipPrintOption]:
        return [
            option_type(self.championship) for option_type in self.available_options()
        ]

    def _get_option[V: ChampionshipPrintOption](self, option_type: type[V]) -> V:
        for option in self.options:
            if isinstance(option, option_type):
                return option
        return option_type(self.championship)

    def option_value(self, option_type: type[ChampionshipPrintOption]) -> Any:
        return self._get_option(option_type).value

    @classmethod
    def is_available(cls, championship: 'Championship') -> bool:
        return True

    @property
    def id(self) -> str:
        return self.static_id()

    @property
    def title(self) -> str:
        return f'{self.championship.name} — {self.label(self.championship)}'

    @property
    def tab_title(self) -> str:
        return self.title


class ChampionshipTournamentListPrintDocument(ChampionshipPrintDocument):
    """The source tournaments, split into those already played and those to
    come. The ``tournament_name`` option chooses how each is named."""

    template_name = 'admin/print/championship_tournaments.html'

    @staticmethod
    def static_id() -> str:
        return 'tournaments'

    @staticmethod
    def label(championship: 'Championship') -> str:
        return _('Tournament list')

    @staticmethod
    def available_options() -> list[type[ChampionshipPrintOption]]:
        return [TournamentNamePrintOption]


class ChampionshipCompetitorListPrintDocument(ChampionshipPrintDocument):
    template_name = 'admin/print/championship_competitors.html'

    @staticmethod
    def static_id() -> str:
        return 'competitors'

    @staticmethod
    def label(championship: 'Championship') -> str:
        if championship.competitor_type == ChampionshipCompetitorType.TEAM:
            return _('Team list')
        return _('Player list')


class ChampionshipRankingsPrintDocument(ChampionshipPrintDocument):
    """The standings. ``sets`` chooses which rankings to print;
    ``include_popover`` adds the per-stage breakdown on hover."""

    template_name = 'admin/print/championship_rankings.html'

    OVERALL_SET = 'overall'

    @staticmethod
    def static_id() -> str:
        return 'rankings'

    @staticmethod
    def label(championship: 'Championship') -> str:
        return _('Rankings')

    @staticmethod
    def available_options() -> list[type[ChampionshipPrintOption]]:
        return [RankingSetsPrintOption, IncludePlayerPopoverPrintOption]

    def selected_set_ids(self) -> list[str]:
        """The ranking sets to print, in display order (overall first, then each
        chosen category). An empty option means every set."""
        available = [self.OVERALL_SET] + [
            str(category.id) for category in self.championship.categories
        ]
        chosen = self.option_value(RankingSetsPrintOption) or []
        if isinstance(chosen, str):
            chosen = [chosen]
        chosen_set = set(chosen)
        selected = [set_id for set_id in available if set_id in chosen_set]
        return selected or available

    def include_popover(self) -> bool:
        return bool(self.option_value(IncludePlayerPopoverPrintOption))


_DOCUMENT_TYPES: tuple[type[ChampionshipPrintDocument], ...] = (
    ChampionshipTournamentListPrintDocument,
    ChampionshipCompetitorListPrintDocument,
    ChampionshipRankingsPrintDocument,
)


def championship_print_documents(
    championship: 'Championship',
) -> list[type[ChampionshipPrintDocument]]:
    """The document types available for this Championship, picker order."""
    return [
        document_type
        for document_type in _DOCUMENT_TYPES
        if document_type.is_available(championship)
    ]


def championship_print_document_type(
    static_id: str,
) -> type[ChampionshipPrintDocument]:
    for document_type in _DOCUMENT_TYPES:
        if document_type.static_id() == static_id:
            return document_type
    raise ValueError(f'Unknown Championship document: {static_id}')
