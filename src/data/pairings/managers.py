from typing import cast, override

from data.pairings import systems, PairingVariation
from data.pairings.systems import PairingSystem
from data.pairings.variations import (
    SwissVariation,
    StandardSwissVariation,
    RoundRobinVariation,
    BergerRoundRobinVariation,
    DoubleBergerRoundRobinVariation,
    TeamSwissVariation,
    StandardTeamSwissVariation,
    TeamRoundRobinVariation,
    BergerTeamRoundRobinVariation,
    DoubleBergerTeamRoundRobinVariation,
    MolterVariation,
    StandardMolterVariation,
)
from plugins.manager import plugin_manager
from utils.entity import EventBoundEntityManager


class PairingSystemManager(EventBoundEntityManager[PairingSystem]):
    @override
    def entity_types(self) -> list[type[PairingSystem]]:
        if self.event is not None and self.event.is_team_event:
            return [
                systems.TeamSwissPairingSystem,
                systems.TeamRoundRobinPairingSystem,
                systems.MolterPairingSystem,
            ]
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


class TeamSwissVariationManager(EventBoundEntityManager[TeamSwissVariation]):
    @override
    def entity_types(self) -> list[type[TeamSwissVariation]]:
        return [StandardTeamSwissVariation]


class TeamRoundRobinVariationManager(EventBoundEntityManager[TeamRoundRobinVariation]):
    @override
    def entity_types(self) -> list[type[TeamRoundRobinVariation]]:
        return [
            BergerTeamRoundRobinVariation,
            DoubleBergerTeamRoundRobinVariation,
        ]


class MolterVariationManager(EventBoundEntityManager[MolterVariation]):
    @override
    def entity_types(self) -> list[type[MolterVariation]]:
        return [StandardMolterVariation]


class PairingVariationManager(EventBoundEntityManager[PairingVariation]):
    @override
    def entity_types(self) -> list[type[PairingVariation]]:
        if self.event is not None and self.event.is_team_event:
            return (
                cast(
                    list[type[PairingVariation]],
                    TeamSwissVariationManager(self.event).entity_types(),
                )
                + cast(
                    list[type[PairingVariation]],
                    TeamRoundRobinVariationManager(self.event).entity_types(),
                )
                + cast(
                    list[type[PairingVariation]],
                    MolterVariationManager(self.event).entity_types(),
                )
            )
        return cast(
            list[type[PairingVariation]],
            SwissVariationManager(self.event).entity_types(),
        ) + cast(
            list[type[PairingVariation]],
            RoundRobinVariationManager(self.event).entity_types(),
        )
