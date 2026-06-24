"""Molter team-pairing system — a fixed-table system whose tables are
produced on the fly by the deterministic core generator
(:func:`data.pairings.molter_generator.generate_molter_table`).

A rule set may override the table for a specific size with an official
table (see :meth:`data.rule_sets.rule_sets.RuleSet.molter_table_overrides`);
that is the one extension point left to downstream consumers.
"""

from functools import cached_property
from typing import TYPE_CHECKING, override

from common.i18n import _
from data.pairings.engines import PairingEngine
from data.pairings.fixed_table import (
    FixedPairingTable,
    FixedTablePairingEngine,
    FixedTablePairingSystem,
    FixedTableVariation,
)
from data.pairings.molter_generator import (
    MolterGenerationError,
    generate_molter_table,
)
from data.pairings.settings import PairingSetting
from data.pairings.systems import SwissPairingSystem
from data.safety_mode import PairingAction, PermissionHandler
from utils.entity import EntityManager, EventBoundEntityManager

if TYPE_CHECKING:
    from data.event import Event
    from data.tournament import Tournament

# Team counts the system offers in the UI. The generator itself handles any
# N >= 3; this caps the UI at a practical maximum.
_SUPPORTED_TEAM_COUNTS: tuple[int, ...] = tuple(range(3, 70))


class MolterPairingSystem(FixedTablePairingSystem):
    @staticmethod
    def static_id() -> str:
        return 'MOLTER'

    @staticmethod
    def static_name() -> str:
        return _('Molter')

    @override
    def variation_manager(self, event: 'Event') -> EntityManager[FixedTableVariation]:
        return MolterVariationManager(event)

    @property
    def pairing_buttons_template(self) -> str:
        return '/admin/pairings/swiss_pairing_buttons.html'

    @property
    @override
    def supports_complementary_pairings(self) -> bool:
        # Molter pairs everyone straight from the fixed table.
        return False

    @cached_property
    def permission_handler(self) -> PermissionHandler[PairingAction]:
        return SwissPairingSystem().permission_handler

    def default_current_round(self, tournament: 'Tournament') -> int:
        return tournament.last_paired_round

    @override
    def get_table(
        self,
        team_count: int,
        players_per_team: int,
        tournament: 'Tournament | None' = None,
    ) -> FixedPairingTable | None:
        # A rule set may ship its own official table for a specific size; it
        # takes precedence over the generated one.
        if tournament is not None:
            rule_set = tournament.rule_set
            if rule_set is not None:
                override_table = rule_set.molter_table_overrides().get(
                    (team_count, players_per_team)
                )
                if override_table is not None:
                    return override_table
        # Otherwise generate the table deterministically. ``None`` for shapes
        # the generator can't satisfy (odd players-per-team, etc.).
        try:
            rounds = tournament.rounds if tournament is not None else None
            return generate_molter_table(team_count, players_per_team, rounds=rounds)
        except MolterGenerationError:
            return None

    @override
    def supported_team_counts(self) -> tuple[int, ...]:
        return _SUPPORTED_TEAM_COUNTS


class MolterEngine(FixedTablePairingEngine):
    @property
    @override
    def system(self) -> MolterPairingSystem:
        return MolterPairingSystem()


class MolterVariation(FixedTableVariation):
    @staticmethod
    def system() -> 'MolterPairingSystem':
        return MolterPairingSystem()

    @property
    def engine(self) -> PairingEngine:
        return MolterEngine()

    @property
    def settings(self) -> list[PairingSetting]:
        return []

    @property
    def trf_encoded_type(self) -> str:
        # No FIDE TRF26 code for Molter; OTHER_ prefix per the convention
        # for non-FIDE acronyms.
        return 'OTHER_MOLTER'


class StandardMolterVariation(MolterVariation):
    @staticmethod
    def variation_id() -> str:
        return 'STANDARD'

    @staticmethod
    def static_name() -> str:
        return _('Standard Molter')


class MolterVariationManager(EventBoundEntityManager[FixedTableVariation]):
    @override
    def entity_types(self) -> list[type[FixedTableVariation]]:
        return [StandardMolterVariation]
