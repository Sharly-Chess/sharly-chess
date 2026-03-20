from data.pairings.systems import SwissPairingSystem, RoundRobinPairingSystem
from data.pairings import PairingSystem
from utils import CoreMapper
from utils.enum import PlayerGender, PlayerRatingType


class SCEPlayerGender(CoreMapper[str, PlayerGender]):
    @classmethod
    def _core_object_by_outer_value(cls) -> dict[str, PlayerGender]:
        return {
            'm': PlayerGender.MALE,
            'w': PlayerGender.FEMALE,
        }


class SCEPlayerRatingType(CoreMapper[str, PlayerRatingType]):
    @classmethod
    def _core_object_by_outer_value(cls) -> dict[str, PlayerRatingType]:
        return {
            'F': PlayerRatingType.FIDE,
            'N': PlayerRatingType.NATIONAL,
            'E': PlayerRatingType.ESTIMATED,
        }


class SCEPairingSystem(CoreMapper[str, PairingSystem]):
    @classmethod
    def _core_object_by_outer_value(cls) -> dict[str, PairingSystem]:
        return {
            'swiss': SwissPairingSystem(),
            'roundrobin': RoundRobinPairingSystem(),
        }
