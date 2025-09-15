from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from common.i18n import _
from data.pairings import systems
from data.pairings.engines import (
    PairingEngine,
    BbpPairings,
    BergerPairingEngine,
    DoubleBergerPairingEngine,
)
from data.pairings.settings import (
    PairingSetting,
    ColorSeedSetting,
    BergerNumbersSetting,
)
from data.pairings.systems import PairingSystem
from data.player import Player
from utils.entity import IdentifiableEntity

if TYPE_CHECKING:
    from data.tournament import Tournament


class PairingVariation(IdentifiableEntity, ABC):
    @classmethod
    def static_id(cls) -> str:
        """Built from the ID of the system and the ID of the variation
        Example for StandardSwissVariation:
        - system: SwissSystem -> SWISS
        - variation: STANDARD
        result: SWISS_STANDARD"""
        return f'{cls.system().id}_{cls.variation_id()}'

    @staticmethod
    @abstractmethod
    def variation_id() -> str:
        """ID of the pairing variation, used to build the ID.
        Should be unique amongst variations of the same system."""

    @staticmethod
    @abstractmethod
    def system() -> PairingSystem:
        """Pairing system associated to the variation."""

    @property
    @abstractmethod
    def engine(self) -> PairingEngine:
        """Pairing engine that generates the pairings of a tournament."""

    @staticmethod
    def print_real_points(current_round: int, rounds: int) -> bool:
        return False

    @property
    @abstractmethod
    def settings(self) -> list[PairingSetting]:
        """List of pairing settings required for the variation to work."""

    @classmethod
    def compute_virtual_points(
        cls,
        tournament: 'Tournament',
        player: Player,
        at_round: int,
    ) -> float:
        """Compute the virtual points of a player for round *at_round*."""
        return 0.0

    def validate_settings(self, tournament: 'Tournament') -> bool:
        return all(setting.is_valid(tournament) for setting in self.settings)

    def settings_tooltip_message(self, tournament: 'Tournament') -> str | None:
        setting_messages = []
        for setting in self.settings:
            message = setting.tooltip_representation(setting.get_value(tournament))
            if message:
                setting_messages.append(
                    _('{string}: {value}').format(string=setting.name, value=message)
                )
        if not setting_messages:
            return None
        return ''.join(
            [
                f'<div class="text-center text-nowrap">{message}</div>'
                for message in setting_messages
            ]
        )


class SwissVariation(PairingVariation, ABC):
    """Variations of the swiss system are accelerations of the pairings.
    It is represented by virtual points attributed to each player during
    the generation of the pairings."""

    @staticmethod
    def system() -> PairingSystem:
        return systems.SwissPairingSystem()

    @property
    def engine(self) -> PairingEngine:
        return BbpPairings()

    @property
    def settings(self) -> list[PairingSetting]:
        return [ColorSeedSetting()]


class RoundRobinVariation(PairingVariation, ABC):
    """Parent class of all the Round-Robin pairing variations."""

    @staticmethod
    def system() -> PairingSystem:
        return systems.RoundRobinPairingSystem()


class StandardSwissVariation(SwissVariation):
    @staticmethod
    def variation_id() -> str:
        return 'STANDARD'

    @staticmethod
    def static_name() -> str:
        return _('Standard swiss system')


class BergerRoundRobinVariation(RoundRobinVariation):
    @staticmethod
    def variation_id() -> str:
        return 'BERGER'

    @staticmethod
    def static_name() -> str:
        return _('Berger')

    @property
    def settings(self) -> list[PairingSetting]:
        return [BergerNumbersSetting()]

    @property
    def engine(self) -> PairingEngine:
        return BergerPairingEngine()


class DoubleBergerRoundRobinVariation(RoundRobinVariation):
    @staticmethod
    def variation_id() -> str:
        return 'DOUBLE_BERGER'

    @staticmethod
    def static_name() -> str:
        return _('Double-round Berger')

    @property
    def settings(self) -> list[PairingSetting]:
        return [BergerNumbersSetting()]

    @property
    def engine(self) -> PairingEngine:
        return DoubleBergerPairingEngine()
