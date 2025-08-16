import re
from decimal import Decimal
from functools import lru_cache, cache
from math import floor
from typing import Callable

import iso4217parse
import pycountry
from babel.numbers import format_currency, format_decimal, get_decimal_symbol
from text_unidecode import unidecode


class StaticUtils:
    """Class containing the static utils functions"""

    PERFORMANCE_TABLE: list[int] = [
        0,
        7,
        14,
        21,
        29,
        36,
        43,
        50,
        57,
        65,
        72,
        80,
        87,
        95,
        102,
        110,
        117,
        125,
        133,
        141,
        149,
        158,
        166,
        175,
        184,
        193,
        202,
        211,
        220,
        230,
        240,
        251,
        262,
        273,
        284,
        296,
        309,
        322,
        336,
        351,
        366,
        383,
        401,
        422,
        444,
        470,
        501,
        538,
        589,
        677,
        800,
    ]

    @classmethod
    @lru_cache(maxsize=32)
    def performance_bonus(cls, fractional_score: float) -> int:
        percent = 100 * fractional_score
        index = floor(abs(50 - percent))
        bonus = cls.PERFORMANCE_TABLE[index]
        if fractional_score < 0.5:
            bonus *= -1
        return bonus

    @staticmethod
    def round_ranking(num: float | Decimal) -> int:
        lowest_int = int(num)
        if num - lowest_int >= 0.5:
            return lowest_int + 1
        return lowest_int

    @staticmethod
    def points_str(points: float | None) -> str:
        if points is None:
            return ''
        points_str = f'{points:.2f}'
        if 0 < points < 1:
            points_str = points_str.replace('0.', '.')
        for old, new in {
            '.00': '',
            '.25': '¼',
            '.50': '½',
            '.75': '¾',
        }.items():
            points_str = points_str.replace(old, new)
        return points_str

    @staticmethod
    def currency_value_str(value: float, currency: str) -> str:
        from common.i18n import get_locale

        locale = get_locale()
        formatted_value = format_currency(value, currency, locale=locale)
        if value.is_integer():
            formatted_value = formatted_value.replace(
                f'{get_decimal_symbol(locale)}00', ''
            )
        return formatted_value

    @staticmethod
    def localized_number(number: float) -> str:
        from common.i18n import get_locale

        return format_decimal(number, locale=get_locale())

    @staticmethod
    @cache
    def get_country_currency(alpha_3_country_code: str) -> str | None:
        country = pycountry.countries.get(alpha_3=alpha_3_country_code)
        if not country:
            return None
        currencies = iso4217parse.by_country(country.alpha_2)
        if not currencies:
            return None
        return currencies[0].alpha3

    @classmethod
    def ordinal_integer(cls, value: int) -> str:
        from common.i18n import get_locale, _

        locale = get_locale()
        affix_fn: Callable[[int], tuple[str, str]]
        match locale:
            case 'en':
                affix_fn = cls._ordinal_affix_en
            case 'fr':
                affix_fn = cls._ordinal_affix_fr
            case _:
                raise NotImplementedError(
                    f'no ordinal affix function for locale {locale}'
                )
        prefix, suffix = affix_fn(value)
        return _('{prefix}{int_value}<sup>{suffix}</sup>').format(
            prefix=prefix, int_value=value, suffix=suffix
        )

    @staticmethod
    @cache
    def _ordinal_affix_en(value: int) -> tuple[str, str]:
        suffix = 'th'
        if not 11 <= value <= 13:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(value % 10, suffix)
        return '', suffix

    @staticmethod
    @cache
    def _ordinal_affix_fr(value: int) -> tuple[str, str]:
        return '', 'er' if value == 1 else 'e'

    @staticmethod
    def name_to_uniq_id(name: str) -> str:
        return re.sub(r'[^a-zA-Z0-9_\-]', '_', unidecode(name).lower())


class SharedUtils:
    """Class containing the shared utils functions,
    i.e. utils functions which can be overwritten by plugins"""

    @staticmethod
    def _get_function(
        plugin_function_name: str, default_function: Callable
    ) -> Callable:
        from plugins.manager import plugin_manager

        return getattr(plugin_manager.hook, plugin_function_name)() or default_function

    @classmethod
    def performance_bonus(cls, fractional_score: float) -> int | float:
        return cls._get_function(
            'get_performance_bonus_function', StaticUtils.performance_bonus
        )(fractional_score)

    @classmethod
    def rounded_performance_bonus(cls, fractional_score: float) -> int:
        return cls.round_ranking(cls.performance_bonus(fractional_score))

    @classmethod
    def round_ranking(cls, num: float | Decimal) -> int:
        return cls._get_function(
            'get_round_ranking_function', StaticUtils.round_ranking
        )(num)
