from abc import ABC, abstractmethod
from dataclasses import dataclass
from itertools import product
from typing import TYPE_CHECKING, Any, Literal

from utils.entity import IdentifiableEntity
from utils.enum import EventType

if TYPE_CHECKING:
    from data.pairings.fixed_table import FixedPairingTable
    from data.teams.team import Team
    from database.sqlite.event.event_store import StoredTournament


@dataclass(frozen=True)
class PointAdjustment:
    """A bonus / penalty a rule set applies to a team for one round.
    ``mp`` / ``gp`` may be negative. ``explanation`` is shown to the
    arbiter (e.g. in the match-score dialog)."""

    mp: float = 0.0
    gp: float = 0.0
    explanation: str = ''


@dataclass(frozen=True)
class RuleSetField:
    """One configuration input a rule set contributes to the tournament
    form. The rule set is the only code that knows what the field means:
    the core renders it, stores its value and hands it back through
    :attr:`RuleSet.config`.

    ``affects_defaults`` marks a field the rule set's ``form_defaults``
    depend on — the modal pre-computes defaults for every combination of
    those, so they must have a finite domain (``select`` / ``bool``).
    ``locked_once_paired`` freezes the field as soon as a round is
    paired, for values (a round count, a scoring scheme) that can't move
    mid-tournament."""

    id: str
    label: str
    kind: Literal['select', 'bool', 'int', 'text'] = 'select'
    default: Any = None
    help_text: str = ''
    # ``select`` only: the (value, label) pairs offered, in display order.
    choices: tuple[tuple[str, str], ...] = ()
    affects_defaults: bool = False
    locked_once_paired: bool = False

    def form_field_name(self, rule_set_id: str) -> str:
        """Name of the HTML input holding this field's value. Namespaced
        by rule set: the modal renders every rule set's fields and only
        enables the selected one's."""
        return f'rule_set_config_{rule_set_id}_{self.id}'

    def values(self) -> tuple[Any, ...]:
        """The field's finite domain, for enumerating default
        combinations. Empty when the domain is open (int / text)."""
        match self.kind:
            case 'select':
                return tuple(value for value, __ in self.choices)
            case 'bool':
                return (False, True)
            case _:
                return ()


def rule_set_config_key(config: dict[str, Any]) -> str:
    """Canonical key for a set of config values, used to look up
    pre-computed form defaults. Mirrored by the tournament modal's JS,
    so keep both sides in step."""
    return '&'.join(
        f'{field_id}={_config_key_value(value)}'
        for field_id, value in sorted(config.items())
    )


def _config_key_value(value: Any) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return '' if value is None else str(value)


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
    when the tournament is created or its rule-set choice is changed.

    A rule set may also declare :attr:`config_fields` — inputs of its
    own the tournament form renders, whose values come back in
    :attr:`config` (stored per tournament in ``rule_set_config``)."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config: dict[str, Any] = dict(config or {})

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

    @property
    def config_fields(self) -> tuple[RuleSetField, ...]:
        """Inputs this rule set adds to the tournament form. The core
        renders them, round-trips their values and stores them; only the
        rule set interprets them. Default: none."""
        return ()

    def config_value(self, field_id: str) -> Any:
        """Value stored for one of the rule set's own fields, falling
        back to the field's default when unset or unknown."""
        for config_field in self.config_fields:
            if config_field.id == field_id:
                value = self.config.get(field_id)
                return config_field.default if value is None else value
        return None

    def validate_config(self, values: dict[str, Any]) -> dict[str, str]:
        """Check the submitted values of :attr:`config_fields` and return
        the errors, keyed by field id. The core already checks types and
        that a ``select`` value is one of its choices; this is for rules
        that span several fields. Default: no error."""
        return {}

    def config_combinations(self) -> list[dict[str, Any]]:
        """Every combination of the ``affects_defaults`` fields' values.
        The tournament modal pre-computes :meth:`form_defaults` for each
        so it can apply them client-side as the arbiter changes them."""
        fields = [
            config_field
            for config_field in self.config_fields
            if config_field.affects_defaults and config_field.values()
        ]
        if not fields:
            return []
        return [
            dict(zip((f.id for f in fields), values))
            for values in product(*(f.values() for f in fields))
        ]

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

    def forced_team_sort_mode(self, pairing_system_id: str | None = None) -> str | None:
        """When set, locks the tournament's team-sort mode to this
        :class:`~utils.enum.TeamSortMode` value — the teams tab shows
        it but won't let the arbiter change it. ``None`` (default)
        leaves the choice free. Regulations usually prescribe an order
        only for the systems that need seeding, hence the pairing system
        id — ``None`` when it can't be resolved."""
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
