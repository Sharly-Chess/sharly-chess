"""FFE Molter pairing system — concrete implementation of the core
:class:`FixedTablePairingSystem` framework, using the official FFE
appointment tables.

Reference: FFE DNA "Tableaux Molter" (October 2025).

The actual lookup-table data lives in :mod:`ffe_molter_tables`.
"""

from functools import cached_property
from typing import TYPE_CHECKING, override

from common.i18n import _
from data.pairings.fixed_table import (
    FixedTablePairingEngine,
    FixedTablePairingSystem,
    FixedTableVariation,
    FixedPairingTable,
)
from data.pairings.engines import PairingEngine
from data.pairings.settings import PairingSetting
from data.pairings.systems import SwissPairingSystem
from data.safety_mode import PermissionHandler, PairingAction
from plugins.ffe.ffe_molter_tables import FFE_MOLTER_TABLES, FFE_MOLTER_TEAM_COUNTS
from utils.entity import EntityManager

if TYPE_CHECKING:
    from data.event import Event
    from data.tournament import Tournament


class FFEMolterPairingSystem(FixedTablePairingSystem):
    @staticmethod
    def static_id() -> str:
        return 'MOLTER'

    @staticmethod
    def static_name() -> str:
        return _('Molter (FFE)')

    @override
    def variation_manager(self, event: 'Event') -> EntityManager[FixedTableVariation]:
        return FFEMolterVariationManager(event)

    @property
    def pairing_buttons_template(self) -> str:
        return '/admin/pairings/swiss_pairing_buttons.html'

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
        # The active rule set may override individual cells of the
        # standard Molter registry (federation cups sometimes ship
        # their own table for a specific size). Fall back to the
        # plugin's registry when nothing overrides.
        if tournament is not None:
            rule_set = tournament.rule_set
            if rule_set is not None:
                override_table = rule_set.molter_table_overrides().get(
                    (team_count, players_per_team)
                )
                if override_table is not None:
                    return override_table
        return FFE_MOLTER_TABLES.get((team_count, players_per_team))

    @override
    def supported_team_counts(self) -> tuple[int, ...]:
        return FFE_MOLTER_TEAM_COUNTS


class FFEMolterEngine(FixedTablePairingEngine):
    @property
    @override
    def system(self) -> FFEMolterPairingSystem:
        return FFEMolterPairingSystem()


class FFEMolterVariation(FixedTableVariation):
    @staticmethod
    def system() -> 'FFEMolterPairingSystem':
        return FFEMolterPairingSystem()

    @property
    def engine(self) -> PairingEngine:
        return FFEMolterEngine()

    @property
    def settings(self) -> list[PairingSetting]:
        return []

    @property
    def trf_encoded_type(self) -> str:
        # No FIDE TRF26 code for Molter; OTHER_ prefix per the
        # convention for non-FIDE acronyms.
        return 'OTHER_FFE_MOLTER'


class StandardFFEMolterVariation(FFEMolterVariation):
    @staticmethod
    def variation_id() -> str:
        return 'STANDARD'

    @staticmethod
    def static_name() -> str:
        return _('Standard FFE Molter')


# Local variation manager so the system can yield its variations without
# core needing to know about the plugin.

from utils.entity import EventBoundEntityManager  # noqa: E402


class FFEMolterVariationManager(EventBoundEntityManager[FixedTableVariation]):
    @override
    def entity_types(self) -> list[type[FixedTableVariation]]:
        return [StandardFFEMolterVariation]
