from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from common.i18n import _
from utils import Utils
from utils.entity import IdentifiableEntity

if TYPE_CHECKING:
    pass


class PrizeType(IdentifiableEntity, ABC):
    @property
    @abstractmethod
    def is_monetary(self) -> bool:
        """Defines if the value of the prize should be considered as a monetary value."""

    @property
    @abstractmethod
    def has_description(self) -> bool:
        """Defines if the prize has a description."""

    @property
    @abstractmethod
    def has_complementary_value(self) -> bool:
        """Defines if the prize has an optional complementary monetary value."""

    @property
    def description_label(self) -> str:
        return _('Description')

    @property
    @abstractmethod
    def tooltip_message(self) -> str:
        """Message of the tooltip displayed on the type select."""

    @classmethod
    @abstractmethod
    def get_prize_name(cls, value: float, description: str, currency: str) -> str:
        """Build the name of the prize according to its type."""

    @classmethod
    def get_prize_full_name(cls, value: float, description: str, currency: str) -> str:
        """Full name of the prize, used on the prize list modal."""
        return cls.get_prize_name(value, description, currency)


class MonetaryPrizeType(PrizeType):
    @staticmethod
    def static_id() -> str:
        return 'MONETARY'

    @staticmethod
    def static_name() -> str:
        return _('Monetary')

    @property
    def is_monetary(self) -> bool:
        return True

    @property
    def has_description(self) -> bool:
        return False

    @property
    def has_complementary_value(self) -> bool:
        return False

    @property
    def tooltip_message(self) -> str:
        return _('Prizes only defined as a monetary value.')

    @classmethod
    def get_prize_name(cls, value: float, description: str, currency: str) -> str:
        return Utils.currency_value_str(value, currency)


class NonMonetaryPrizeType(PrizeType):
    @staticmethod
    def static_id() -> str:
        return 'NON_MONETARY'

    @staticmethod
    def static_name() -> str:
        return _('Non-monetary')

    @property
    def is_monetary(self) -> bool:
        return False

    @property
    def has_description(self) -> bool:
        return True

    @property
    def has_complementary_value(self) -> bool:
        return False

    @property
    def tooltip_message(self) -> str:
        return _(
            'Prizes defined as a free text field. The value is used '
            'to determine the place of the prize in the list.'
        )

    @classmethod
    def get_prize_name(cls, value: float, description: str, currency: str) -> str:
        return description

    @classmethod
    def get_prize_full_name(cls, value: float, description: str, currency: str) -> str:
        if not value:
            return description
        value_str = _('value: {value}').format(value=Utils.localized_number(value))
        return f'{description} ({value_str})'


class HybridPrizeType(PrizeType):
    @staticmethod
    def static_id() -> str:
        return 'HYBRID'

    @staticmethod
    def static_name() -> str:
        return _('Hybrid')

    @property
    def is_monetary(self) -> bool:
        return True

    @property
    def has_description(self) -> bool:
        return True

    @property
    def has_complementary_value(self) -> bool:
        return True

    @property
    def description_label(self) -> str:
        return _('Complementary prize')

    @property
    def tooltip_message(self) -> str:
        return _(
            'Prizes defined as both a monetary value and a complementary '
            'non-monetary prize (example: 100 € + Trophy).'
        )

    @classmethod
    def get_prize_name(cls, value: float, description: str, currency: str) -> str:
        return f'{Utils.currency_value_str(value, currency)} + {description}'
