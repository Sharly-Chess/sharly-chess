from typing import cast, override

from data.pairings import systems, PairingVariation
from data.pairings.molter import MolterPairingSystem, MolterVariationManager
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
    TeamTwoGameMatchVariation,
    StandardTeamTwoGameMatchVariation,
)
from plugins.manager import plugin_manager
from utils.entity import EventBoundEntityManager


class PairingSystemManager(EventBoundEntityManager[PairingSystem]):
    @override
    def entity_types(self) -> list[type[PairingSystem]]:
        if self.event is not None and self.event.is_team_event:
            base: list[type[PairingSystem]] = [
                systems.TeamSwissPairingSystem,
                systems.TeamRoundRobinPairingSystem,
                systems.TeamTwoGameMatchPairingSystem,
                MolterPairingSystem,
            ]
            plugin_manager.hook_for_event(self.event, 'insert_team_pairing_systems')(
                pairing_systems=base
            )
            return base
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


class TeamTwoGameMatchVariationManager(
    EventBoundEntityManager[TeamTwoGameMatchVariation]
):
    @override
    def entity_types(self) -> list[type[TeamTwoGameMatchVariation]]:
        return [StandardTeamTwoGameMatchVariation]


class PairingVariationManager(EventBoundEntityManager[PairingVariation]):
    @override
    def entity_types(self) -> list[type[PairingVariation]]:
        if self.event is not None and self.event.is_team_event:
            result: list[type[PairingVariation]] = (
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
                    TeamTwoGameMatchVariationManager(self.event).entity_types(),
                )
                + cast(
                    list[type[PairingVariation]],
                    MolterVariationManager(self.event).entity_types(),
                )
            )
            plugin_manager.hook_for_event(self.event, 'insert_team_pairing_variations')(
                variations=result
            )
            return result
        return cast(
            list[type[PairingVariation]],
            SwissVariationManager(self.event).entity_types(),
        ) + cast(
            list[type[PairingVariation]],
            RoundRobinVariationManager(self.event).entity_types(),
        )
