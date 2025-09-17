from collections.abc import Callable
from operator import attrgetter
import unicodedata
from string import capwords
from babel import Locale
from typing import Any


def locale_flag_url(locale: str):
    """Returns the uri of a locale to the image of its flag."""
    return f'/static/images/locales/{locale}.svg'


def locale_localized_name(locale: str) -> str:
    """Returns the locale in its own language."""
    return capwords(str(Locale.parse(locale).get_display_name()))


def unicode_normalize(string: str) -> str:
    """Removes the accents of the string, cf https://www.unicode.org/reports/tr15/#Norm_Forms"""
    return ''.join(
        filter(
            lambda c: not unicodedata.combining(c),
            unicodedata.normalize('NFKD', string),
        )
    )


def normalized_key(s: str | None) -> str:
    """Normalize and casefold a string for consistent comparisons.
    None is treated as empty string.
    """
    if s is None:
        return ''
    return unicodedata.normalize('NFKD', str(s)).casefold()


def by(*attrs: str) -> Callable[[Any], tuple[str, ...]]:
    """Return a normalized sort key function for one or more string attributes."""
    getters = [attrgetter(a) for a in attrs]
    return lambda obj: tuple(normalized_key(g(obj)) for g in getters)
