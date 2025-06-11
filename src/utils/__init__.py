from decimal import Decimal
from functools import lru_cache, cache
from math import floor
from typing import Callable


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
        from common.i18n import _

        return _('{currency}{value}').format(
            currency=currency,
            value=int(value) if value.is_integer() else f'{value:.2f}',
        )

    @staticmethod
    @cache
    def ordinal_suffix(value: int) -> str:
        from common.i18n import _

        if value == 1:
            return _('st *** ORDINAL SUFFIX 1')
        if not 11 <= value <= 13:
            match value % 10:
                case 1:
                    return _('st *** ORDINAL SUFFIX LAST DIGIT 1')
                case 2:
                    return _('nd *** ORDINAL SUFFIX LAST DIGIT 2')
                case 3:
                    return _('rd *** ORDINAL SUFFIX LAST DIGIT 3')
        return _('th *** DEFAULT ORDINAL SUFFIX')


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
