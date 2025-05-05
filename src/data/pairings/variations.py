from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from common.i18n import _
from data.pairings import systems
from data.pairings.engines import PairingEngine, BbpPairings, RoundRobinPairingEngine
from data.pairings.settings import PairingSetting, ColorSeedSetting
from data.pairings.systems import PairingSystem
from data.player import Player
from utils.entity import IdentifiableEntity

if TYPE_CHECKING:
    from data.tournament import Tournament


class PairingVariation(IdentifiableEntity, ABC):
    @classmethod
    def static_id(cls) -> str:
        return f'{cls.system().id}_{cls.variation_id()}'

    @staticmethod
    @abstractmethod
    def variation_id() -> str:
        """ID of the pairing variation.
        Should be unique amongst variations of the same system."""

    @staticmethod
    @abstractmethod
    def system() -> PairingSystem:
        """Pairing system associated to the variation."""

    @property
    @abstractmethod
    def engine(self) -> PairingEngine:
        """Pairing engine that generates the pairings of a tournament."""

    @property
    def is_pairing_generation_implemented(self) -> bool:
        """Flag replacing the 'Pair' button by a
        'Generate pairings in Papi' message."""
        # TODO remove once all Papi pairing variations have been implemented
        return True

    @staticmethod
    def print_real_points(current_round: int, rounds: int) -> bool:
        return False

    @property
    @abstractmethod
    def settings(self) -> list[PairingSetting]:
        """List of pairing settings required for the variation to work."""

    @staticmethod
    def compute_virtual_points(
        tournament: 'Tournament',
        player: Player,
        at_round: int,
    ) -> float:
        """Compute the virtual points of a player for round *at_round*."""
        return 0.0

    def validate_settings(self, tournament: 'Tournament') -> bool:
        return all(
            setting.is_set(tournament) and setting.is_valid(tournament)
            for setting in self.settings
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

    @property
    def engine(self) -> PairingEngine:
        return RoundRobinPairingEngine()


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
    def is_pairing_generation_implemented(self) -> bool:
        return False

    @property
    def settings(self) -> list[PairingSetting]:
        return []
