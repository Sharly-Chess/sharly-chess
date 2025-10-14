from typing import cast, override

from data.pairings import systems, PairingVariation
from data.pairings.systems import PairingSystem
from data.pairings.variations import (
    SwissVariation,
    StandardSwissVariation,
    RoundRobinVariation,
    BergerRoundRobinVariation,
    DoubleBergerRoundRobinVariation,
)
from plugins.manager import plugin_manager
from utils.entity import EntityManager, EventBoundEntityManager


class PairingSystemManager(EntityManager[PairingSystem]):
    @override
    def entity_types(self) -> list[type[PairingSystem]]:
        return [
            systems.SwissPairingSystem,
            systems.RoundRobinPairingSystem,
        ]


class SwissVariationManager(EventBoundEntityManager[SwissVariation]):
    @override
    def entity_types(self) -> list[type[SwissVariation]]:
        variations: list[type[SwissVariation]] = [StandardSwissVariation]
        plugin_manager.hook_for_event(
            self.event, 'insert_swiss_pairing_variation_types'
        )(variation_types=variations)
        return variations


class RoundRobinVariationManager(EventBoundEntityManager[RoundRobinVariation]):
    @override
    def entity_types(self) -> list[type[RoundRobinVariation]]:
        return [
            BergerRoundRobinVariation,
            DoubleBergerRoundRobinVariation,
        ]


class PairingVariationManager(EventBoundEntityManager[PairingVariation]):
    @override
    def entity_types(self) -> list[type[PairingVariation]]:
        return cast(
            list[type[PairingVariation]],
            SwissVariationManager(self.event).entity_types(),
        ) + cast(
            list[type[PairingVariation]],
            RoundRobinVariationManager(self.event).entity_types(),
        )
