from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from utils.entity import IdentifiableEntity
from utils.enum import EventType

if TYPE_CHECKING:
    from data.pairings.fixed_table import FixedPairingTable
    from data.team import Team
    from database.sqlite.event.event_store import StoredTournament


@dataclass(frozen=True)
class PointAdjustment:
    """A bonus / penalty a rule set applies to a team for one round.
    ``mp`` / ``gp`` may be negative. ``explanation`` is shown to the
    arbiter (e.g. in the match-score dialog)."""

    mp: float = 0.0
    gp: float = 0.0
    explanation: str = ''


class RuleSet(IdentifiableEntity, ABC):
    """An official rule set (e.g. a national federation cup) that
    pre-configures a tournament for a specific competition format.

    A rule set is plugin-contributed via the ``insert_rule_sets`` hook
    and selected by the arbiter when creating a tournament. The picker
    in the tournament modal filters by :attr:`event_type` and is
    hidden entirely when no plugin contributes a rule set matching the
    event type.

    A rule set is non-coercive: the arbiter still picks the pairing
    variation (Swiss / Molter / round-robin) themselves and creates one
    tournament per phase / group. The rule set just supplies the right
    defaults (match-point system, tie-break list, game-point overrides)
    when the tournament is created or its rule-set choice is changed."""

    @staticmethod
    @abstractmethod
    def static_id() -> str:
        """Stable id stored in the DB (``tournament.rule_set``)."""

    @staticmethod
    @abstractmethod
    def static_name() -> str:
        """Display name shown in the picker."""

    @property
    def description(self) -> str:
        """Short tooltip shown next to the picker (optional)."""
        return ''

    @property
    @abstractmethod
    def event_type(self) -> EventType:
        """Which event type this rule set targets — controls picker
        visibility (the picker filters down to the current event's
        type and is hidden when nothing matches)."""

    def apply_defaults(
        self,
        stored_tournament: 'StoredTournament',
        pairing_system_id: str | None = None,
    ) -> None:
        """Populate the rule-set's default values on the given stored
        tournament. Called when the rule set is selected or the
        tournament is saved. Sub-classes mutate ``stored_tournament``
        in place — match-point system, game-point overrides, team-
        player count, colour pattern, etc.

        ``pairing_system_id`` is the id of the chosen pairing system
        (``SWISS``, ``ROUND_ROBIN``, ``MOLTER``, …), or ``None`` if
        the system can't be resolved at call time; sub-classes may
        switch their defaults based on it (e.g. Molter scoring vs
        Swiss-style).

        Default: no-op."""

    @property
    def managed_fields(self) -> set[str]:
        """HTML form-field names the rule set fully controls. The
        tournament modal disables these inputs with a 'set by rule
        set X' tooltip when the rule set is picked — the values the
        user sees come from :meth:`apply_defaults` and the form's
        submitted values are overridden on save."""
        return set()

    def form_defaults(
        self,
        pairing_system_id: str | None = None,
        pairing_variation_id: str | None = None,
    ) -> dict[str, str]:
        """Form-data string values for the rule set's managed fields,
        possibly varying with the chosen pairing system (different
        primary score / scoring values / round counts per system).
        ``pairing_variation_id`` is the full variation id (system +
        variation) for defaults that differ between variations of one
        system — e.g. single vs double round-robin round counts. Used
        by the modal JS to populate inputs when the rule set or pairing
        changes. Sub-classes override; default empty."""
        return {}

    @property
    def roster_max_size(self) -> int | None:
        """Maximum number of players a team may carry on its roster.
        ``None`` (default) means uncapped."""
        return None

    @property
    def forced_prohibited_pairing(self) -> tuple[str, bool] | None:
        """When set, ``(dimension_id, is_hard)`` the rule set imposes
        for the tournament's prohibited pairings — the protection
        modal shows the configuration read-only. ``None`` (default)
        leaves the configuration free."""
        return None

    @property
    def forced_team_sort_mode(self) -> str | None:
        """When set, locks the tournament's team-sort mode to this
        :class:`~utils.enum.TeamSortMode` value — the teams tab shows
        it but won't let the arbiter change it. ``None`` (default)
        leaves the choice free."""
        return None

    def rounds_for_pairing(
        self,
        pairing_system_id: str,
        pairing_variation_id: str | None = None,
    ) -> int | None:
        """Round count this rule set imposes for the given pairing
        system / variation. ``None`` (default) means no lock — the
        arbiter chooses freely. ``pairing_variation_id`` lets the count
        differ between variations of one system (e.g. a double
        round-robin runs fewer rounds than the single one). When set,
        :meth:`apply_defaults` writes the value on save and the
        tournament modal locks the ``rounds`` field."""
        return None

    def molter_table_overrides(self) -> dict[tuple[int, int], 'FixedPairingTable']:
        """Per-rule-set overrides for the fixed Molter pairing tables,
        keyed by ``(team_count, players_per_team)``. The Molter
        pairing system consults this map first and falls back to its
        own registry when no override is set. Default: empty."""
        return {}

    def roster_warnings(self, team: 'Team') -> list[str]:
        """Inspect ``team``'s roster and return zero or more warning
        messages — anything the regulations flag without hard-blocking
        (rating ceilings, composition rules, etc.). Empty list means
        the roster is clean from this rule set's perspective.

        Surfaced as a triangle + tooltip on the team card. Plugins
        encapsulate every cup-specific check here so the core stays
        agnostic of any one federation's rule shape."""
        return []

    @property
    def tie_break_overrides_by_pairing(self) -> dict[str, list[tuple[str, dict]]]:
        """Per pairing-system id, the ordered ``(tie_break_type_id,
        options)`` list the rule set imposes. When non-empty for the
        tournament's pairing system, the standings tie-breaks are
        replaced on every save and the tie-break editor renders
        read-only. Sub-classes override; default is empty."""
        return {}

    def tie_breaks_for_pairing(self, pairing_id: str) -> list[tuple[str, dict]]:
        return self.tie_break_overrides_by_pairing.get(pairing_id, [])

    def team_point_adjustment(
        self, team: 'Team', round_: int
    ) -> 'PointAdjustment | None':
        """Bonus / penalty points this rule set assigns to ``team`` for
        ``round_``, with a human-readable explanation. Returns ``None``
        when the rule set imposes no adjustment (the default). Added on
        top of any manual adjustment the arbiter enters."""
        return None
