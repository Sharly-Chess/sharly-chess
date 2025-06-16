from abc import ABC

from common.i18n import _
from utils.entity import IdentifiableEntity


class Currency(IdentifiableEntity, ABC):
    @property
    def babel_value(self) -> str:
        """Value passed to the babel.numbers.format_currency.
        Defaults to the ID, can also be the symbol of the currency."""
        return self.id


class EuroCurrency(Currency):
    @staticmethod
    def static_id() -> str:
        return 'EUR'

    @staticmethod
    def static_name() -> str:
        return _('Euro')


class DollarCurrency(Currency):
    @staticmethod
    def static_id() -> str:
        return 'USD'

    @staticmethod
    def static_name() -> str:
        return _('US Dollar')


class PoundSterlingCurrency(Currency):
    @staticmethod
    def static_id() -> str:
        return 'GBP'

    @staticmethod
    def static_name() -> str:
        return _('Pound Sterling')
