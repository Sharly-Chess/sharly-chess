from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from common.i18n import _
from utils.entity import IdentifiableEntity, EntityManager

if TYPE_CHECKING:
    from data.pairings.variations import PairingVariation


class PairingSystem(IdentifiableEntity, ABC):
    """Abstract class representing all the different pairing systems.
    Each system can have different variations."""

    @property
    @abstractmethod
    def variation_manager(self) -> EntityManager['PairingVariation']:
        """Manager of all the variations of the system."""

    @property
    def variation_field_id(self) -> str:
        """ID of the form field selecting the variation of the system."""
        return f'{self.id}_pairing_variation'

    @property
    def variation_container_id(self) -> str:
        """ID of the container of the variation field in the form."""
        return f'{self.variation_field_id}_container'


class SwissPairingSystem(PairingSystem):
    @staticmethod
    def static_id() -> str:
        return 'SWISS'

    @staticmethod
    def static_name() -> str:
        return _('Swiss')

    @property
    def variation_manager(self) -> EntityManager['PairingVariation']:
        from data.pairings.managers import SwissVariationManager

        return SwissVariationManager()  # type: ignore


class RoundRobinPairingSystem(PairingSystem):
    @staticmethod
    def static_id() -> str:
        return 'ROUND_ROBIN'

    @staticmethod
    def static_name() -> str:
        return _('Round-Robin')

    @property
    def variation_manager(self) -> EntityManager['PairingVariation']:
        from data.pairings.managers import RoundRobinVariationManager

        return RoundRobinVariationManager()  # type: ignore
