from abc import ABC, abstractmethod
from functools import cached_property
from typing import TYPE_CHECKING, override

from common.i18n import _
from data.safety_mode import (
    PairingAction,
    PermissionHandler,
    Permission,
    RoundStatus,
    SafetyMode,
)
from utils.entity import IdentifiableEntity, EntityManager

if TYPE_CHECKING:
    from data.pairings.variations import (
        PairingVariation,
        SwissVariation,
        RoundRobinVariation,
        TeamSwissVariation,
        TeamRoundRobinVariation,
    )
    from data.tournament import Tournament
    from data.event import Event


class PairingSystem[PV: PairingVariation](IdentifiableEntity, ABC):
    """Abstract class representing all the different pairing systems.
    Each system can have different variations."""

    @abstractmethod
    def variation_manager(self, event: 'Event') -> EntityManager[PV]:
        """Manager of all the variations of the system."""

    @property
    @abstractmethod
    def pairing_buttons_template(self) -> str:
        """Template of the buttons handling the pairings."""

    @cached_property
    @abstractmethod
    def permission_handler(self) -> PermissionHandler[PairingAction]:
        """Handler of permissions for the pairing system."""

    @abstractmethod
    def default_current_round(self, tournament: 'Tournament') -> int:
        """Get the current round to use as default when it is not defined in the DB."""

    @property
    def allow_rounds_update_once_started(self) -> bool:
        """Determines if the number of rounds can be updated once a tournament is started."""
        return True

    @property
    def allow_player_addition_once_paired(self) -> bool:
        """Determines if players can be added on a tournament with pairings."""
        return True

    @property
    def allow_bye_definition(self) -> bool:
        """Determines if byes can be defined from the player history modal."""
        return True

    @property
    def show_unfinished_round_modal(self) -> bool:
        """Determines if the modal warning about the round not being finished
        when moving from the current to the next round is displayed."""
        return True

    @property
    def show_unpaired_player_modal(self) -> bool:
        """Determines if the modal allowing to handle unpaired players is displayed."""
        return True

    @property
    def split_unpaired_and_bye_players(self) -> bool:
        """Determines if the unpaired and bye players are separated in the unpaired table."""
        return True

    @property
    def round_per_round_pairing_generation(self) -> bool:
        """Determines if the pairings are generated round per round
        or all the rounds at the same time."""
        return True

    @property
    def paired_by_team(self) -> bool:
        """Whether this system pairs entire teams against each other (each
        round groups boards into team-vs-team blocks). True for the standard
        team systems; False for individual systems and for team systems
        like flat-mixed-pairing systems where boards aren't grouped.
        Default True — most team systems pair by team; non-team systems
        override to False."""
        return True

    @property
    def variation_field_id(self) -> str:
        """ID of the form field selecting the variation of the system."""
        return f'{self.id}_pairing_variation'

    @property
    def variation_container_id(self) -> str:
        """ID of the container of the variation field in the form."""
        return f'{self.variation_field_id}_container'

    @property
    def tie_break_help_container_id(self) -> str:
        """ID of the html element containing the tie-break help in the tournament form."""
        return f'{self.id}_tie_break_help_container'


class SwissPairingSystem(PairingSystem['SwissVariation']):
    @staticmethod
    def static_id() -> str:
        return 'SWISS'

    @staticmethod
    def static_name() -> str:
        return _('Swiss')

    @override
    def variation_manager(self, event: 'Event') -> EntityManager['SwissVariation']:
        from data.pairings.managers import SwissVariationManager

        return SwissVariationManager(event)

    @property
    def pairing_buttons_template(self) -> str:
        return '/admin/pairings/swiss_pairing_buttons.html'

    @cached_property
    def permission_handler(self) -> PermissionHandler[PairingAction]:
        permissions = [
            Permission(PairingAction.FULL_PAIRING, {RoundStatus.NEXT: SafetyMode.SAFE}),
            Permission(
                PairingAction.PARTIAL_PAIRING, {RoundStatus.CURRENT: SafetyMode.UNSAFE}
            ),
            Permission(
                PairingAction.MANUAL_PAIRING,
                {
                    RoundStatus.PAST: SafetyMode.FIDE_INCOMPATIBLE,
                    RoundStatus.PREVIOUS: SafetyMode.UNSAFE,
                    RoundStatus.CURRENT: SafetyMode.UNSAFE,
                    RoundStatus.NEXT: SafetyMode.FIDE_INCOMPATIBLE,
                },
            ),
            Permission(
                PairingAction.FULL_UNPAIRING,
                {RoundStatus.CURRENT: SafetyMode.FIDE_INCOMPATIBLE},
            ),
            Permission(
                PairingAction.MANUAL_UNPAIRING,
                {
                    RoundStatus.PAST: SafetyMode.FIDE_INCOMPATIBLE,
                    RoundStatus.PREVIOUS: SafetyMode.UNSAFE,
                    RoundStatus.CURRENT: SafetyMode.UNSAFE,
                },
            ),
            Permission(
                PairingAction.COLOR_PERMUTE,
                {
                    RoundStatus.PAST: SafetyMode.FIDE_INCOMPATIBLE,
                    RoundStatus.PREVIOUS: SafetyMode.UNSAFE,
                    RoundStatus.CURRENT: SafetyMode.UNSAFE,
                },
            ),
            Permission(
                PairingAction.RESULT_UPDATE,
                {
                    RoundStatus.PAST: SafetyMode.FIDE_INCOMPATIBLE,
                    RoundStatus.PREVIOUS: SafetyMode.UNSAFE,
                    RoundStatus.CURRENT: SafetyMode.SAFE,
                },
            ),
            Permission(
                PairingAction.BYE_UPDATE,
                {
                    RoundStatus.PAST: SafetyMode.FIDE_INCOMPATIBLE,
                    RoundStatus.PREVIOUS: SafetyMode.UNSAFE,
                    RoundStatus.CURRENT: SafetyMode.SAFE,
                    RoundStatus.NEXT: SafetyMode.SAFE,
                    RoundStatus.FUTURE: SafetyMode.SAFE,
                },
            ),
        ]
        return PermissionHandler(permissions)

    def default_current_round(self, tournament: 'Tournament') -> int:
        return tournament.last_paired_round


class RoundRobinPairingSystem(PairingSystem['RoundRobinVariation']):
    @staticmethod
    def static_id() -> str:
        return 'ROUND_ROBIN'

    @staticmethod
    def static_name() -> str:
        return _('Round-Robin')

    @property
    def round_per_round_pairing_generation(self) -> bool:
        return False

    @override
    def variation_manager(self, event: 'Event') -> EntityManager['RoundRobinVariation']:
        from data.pairings.managers import RoundRobinVariationManager

        return RoundRobinVariationManager(event)

    @property
    def allow_rounds_update_once_started(self) -> bool:
        return False

    @property
    def allow_player_addition_once_paired(self) -> bool:
        return False

    @property
    def allow_bye_definition(self) -> bool:
        return False

    @property
    def show_unfinished_round_modal(self) -> bool:
        return False

    @property
    def show_unpaired_player_modal(self) -> bool:
        return False

    @property
    def split_unpaired_and_bye_players(self) -> bool:
        return False

    @property
    def pairing_buttons_template(self) -> str:
        return '/admin/pairings/round_robin_pairing_buttons.html'

    @cached_property
    def permission_handler(self) -> PermissionHandler[PairingAction]:
        permissions = [
            Permission(
                PairingAction.RESULT_UPDATE,
                {
                    RoundStatus.PAST: SafetyMode.UNSAFE,
                    RoundStatus.PREVIOUS: SafetyMode.UNSAFE,
                    RoundStatus.CURRENT: SafetyMode.SAFE,
                    RoundStatus.NEXT: SafetyMode.SAFE,
                    RoundStatus.FUTURE: SafetyMode.SAFE,
                },
            ),
            Permission(
                PairingAction.COLOR_PERMUTE,
                {status: SafetyMode.FIDE_INCOMPATIBLE for status in RoundStatus},
            ),
        ]
        return PermissionHandler(permissions)

    def default_current_round(self, tournament: 'Tournament') -> int:
        """Last round with played results."""
        return next(
            (
                round_
                for round_ in reversed(range(1, tournament.rounds + 1))
                if tournament.round_has_played_result(round_)
            ),
            1 if tournament.has_pairings else 0,
        )


# ---------------------------------------------------------------------------------
# Team pairing systems. Engines / variations live in variations.py / engines.py.
# These mirror their individual counterparts; specific team-mode behaviour will
# land alongside the engine implementations in future bites.
# ---------------------------------------------------------------------------------


class TeamSwissPairingSystem(PairingSystem['TeamSwissVariation']):
    @staticmethod
    def static_id() -> str:
        return 'TEAM_SWISS'

    @staticmethod
    def static_name() -> str:
        return _('Team Swiss')

    @override
    def variation_manager(self, event: 'Event') -> EntityManager['TeamSwissVariation']:
        from data.pairings.managers import TeamSwissVariationManager

        return TeamSwissVariationManager(event)

    @property
    def pairing_buttons_template(self) -> str:
        return '/admin/pairings/swiss_pairing_buttons.html'

    @cached_property
    def permission_handler(self) -> PermissionHandler[PairingAction]:
        return SwissPairingSystem().permission_handler

    def default_current_round(self, tournament: 'Tournament') -> int:
        return tournament.last_paired_round


class TeamRoundRobinPairingSystem(PairingSystem['TeamRoundRobinVariation']):
    @staticmethod
    def static_id() -> str:
        return 'TEAM_ROUND_ROBIN'

    @staticmethod
    def static_name() -> str:
        return _('Team Round-Robin')

    @property
    def round_per_round_pairing_generation(self) -> bool:
        return False

    @override
    def variation_manager(
        self, event: 'Event'
    ) -> EntityManager['TeamRoundRobinVariation']:
        from data.pairings.managers import TeamRoundRobinVariationManager

        return TeamRoundRobinVariationManager(event)

    @property
    def allow_rounds_update_once_started(self) -> bool:
        return False

    @property
    def allow_player_addition_once_paired(self) -> bool:
        return False

    @property
    def allow_bye_definition(self) -> bool:
        return False

    @property
    def show_unfinished_round_modal(self) -> bool:
        return False

    @property
    def show_unpaired_player_modal(self) -> bool:
        return False

    @property
    def split_unpaired_and_bye_players(self) -> bool:
        return False

    @property
    def pairing_buttons_template(self) -> str:
        return '/admin/pairings/round_robin_pairing_buttons.html'

    @cached_property
    def permission_handler(self) -> PermissionHandler[PairingAction]:
        return RoundRobinPairingSystem().permission_handler

    def default_current_round(self, tournament: 'Tournament') -> int:
        return next(
            (
                round_
                for round_ in reversed(range(1, tournament.rounds + 1))
                if tournament.round_has_played_result(round_)
            ),
            1 if tournament.has_pairings else 0,
        )
