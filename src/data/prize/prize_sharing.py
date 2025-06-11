from abc import ABC

from common.i18n import _
from utils.entity import IdentifiableEntity


class PrizeSharing(IdentifiableEntity, ABC):
    """Class defining the way to share prizes when two or more
    players with the same points are eligible for prizes."""


class NoPrizeSharing(PrizeSharing):
    @staticmethod
    def static_id() -> str:
        return 'NONE'

    @staticmethod
    def static_name() -> str:
        return _('None')


class AveragePrizeSharing(PrizeSharing):
    @staticmethod
    def static_id() -> str:
        return 'AVERAGE'

    @staticmethod
    def static_name() -> str:
        return _('Average')


class HortSystemPrizeSharing(PrizeSharing):
    @staticmethod
    def static_id() -> str:
        return 'HORT_SYSTEM'

    @staticmethod
    def static_name() -> str:
        return _('Hort system')
