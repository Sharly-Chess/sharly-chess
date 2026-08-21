"""Printable Championship documents.

Championship is not event-bound, so it has its own light document layer that
mirrors the event print pattern (a manager exposing document types, each with a
print template). The actual page data is assembled by the controller from the
existing ranking/competitor helpers; a document here only carries its identity,
label, template and option schema."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from common.i18n import _
from data.championship.options import ChampionshipCompetitorType

if TYPE_CHECKING:
    from data.championship.championship import Championship


class ChampionshipPrintDocument(ABC):
    """A printable Championship document. Instances are cheap value objects passed
    to the print template (which reads ``id`` / ``title`` / ``tab_title``)."""

    #: Print template extending ``admin/print/base.html``.
    template_name: str

    def __init__(self, championship: 'Championship', options: dict | None = None):
        self.championship = championship
        self.options = options or {}

    @staticmethod
    @abstractmethod
    def static_id() -> str:
        """Stable id used in the document URL and the picker."""

    @staticmethod
    @abstractmethod
    def label(championship: 'Championship') -> str:
        """Translated name for the picker (may depend on individual vs team)."""

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
    """The standings. The ``sets`` option chooses which rankings to print — the
    overall ranking and/or specific category rankings (default: all)."""

    template_name = 'admin/print/championship_rankings.html'

    OVERALL_SET = 'overall'

    @staticmethod
    def static_id() -> str:
        return 'rankings'

    @staticmethod
    def label(championship: 'Championship') -> str:
        return _('Rankings')

    def selected_set_ids(self) -> list[str]:
        """The ranking sets to print, in display order (overall first, then each
        chosen category). An empty/absent option means every set."""
        available = [self.OVERALL_SET] + [
            str(category.id) for category in self.championship.categories
        ]
        chosen = self.options.get('sets') or []
        if isinstance(chosen, str):
            chosen = [chosen]
        chosen_set = set(chosen)
        selected = [set_id for set_id in available if set_id in chosen_set]
        return selected or available


def championship_print_documents(
    championship: 'Championship',
) -> list[type[ChampionshipPrintDocument]]:
    """The document types available for this Championship, picker order."""
    return [
        document_type
        for document_type in (
            ChampionshipCompetitorListPrintDocument,
            ChampionshipRankingsPrintDocument,
        )
        if document_type.is_available(championship)
    ]


def championship_print_document_type(
    static_id: str,
) -> type[ChampionshipPrintDocument]:
    for document_type in (
        ChampionshipCompetitorListPrintDocument,
        ChampionshipRankingsPrintDocument,
    ):
        if document_type.static_id() == static_id:
            return document_type
    raise ValueError(f'Unknown Championship document: {static_id}')
