from data.pairings import systems, PairingVariation
from data.pairings.systems import PairingSystem
from data.pairings.variations import (
    SwissVariation,
    StandardSwissVariation,
    RoundRobinVariation,
    BergerRoundRobinVariation,
)
from plugins.manager import plugin_manager
from utils.entity import EntityManager


class PairingSystemManager(EntityManager[PairingSystem]):
    @staticmethod
    def entity_types() -> list[type[PairingSystem]]:
        return [
            systems.SwissPairingSystem,
            systems.RoundRobinPairingSystem,
        ]


class SwissVariationManager(EntityManager[SwissVariation]):
    @staticmethod
    def entity_types() -> list[type[SwissVariation]]:
        variations: list[type[SwissVariation]] = [StandardSwissVariation]
        plugin_manager.hook.insert_swiss_pairing_variation_types(
            variation_types=variations
        )
        return variations


class RoundRobinVariationManager(EntityManager[RoundRobinVariation]):
    @staticmethod
    def entity_types() -> list[type[RoundRobinVariation]]:
        return [BergerRoundRobinVariation]


class PairingVariationManager(EntityManager[PairingVariation]):
    @staticmethod
    def entity_types() -> list[type[PairingVariation]]:
        variations: list[type[PairingVariation]] = (
            SwissVariationManager.entity_types()
            + RoundRobinVariationManager.entity_types()
        )
        return variations
