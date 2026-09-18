from collections.abc import Callable
from functools import cache
from operator import attrgetter
import unicodedata
from string import capwords
from babel import Locale
from typing import Any

from jinja2 import TemplateError


def locale_flag_url(locale: str) -> str:
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


def parse_jinja_string(
    template_string: str,
    context: dict[str, Any] | None = None,
    on_error: str | None = None,
) -> str:
    from web.settings import template_engine

    try:
        return template_engine.render_string(
            template_string=template_string,
            context=context or {},
        )
    except TemplateError as te:
        return on_error or str(te)


def parse_jinja_template(
    template_name: str,
    context: dict[str, Any] | None = None,
    on_error: str | None = None,
) -> str:
    from web.settings import template_engine

    try:
        return template_engine.get_template(template_name).render(context)
    except TemplateError as te:
        return on_error or str(te)


# ---------------------------------------------------------------------------
# Ordinals
# ---------------------------------------------------------------------------

# Letters an ordinal ends with, per language. The plural is the stage names'
# ('8es de finale'), which name an ordinal rather than count with it, so it
# never comes out of the affix functions below.
_ORDINAL_SUFFIXES: dict[str, tuple[str, ...]] = {
    'en': ('st', 'nd', 'rd', 'th'),
    'fr': ('er', 'e', 'es'),
}


def ordinal_suffixes() -> tuple[str, ...]:
    """Every ending an ordinal may take in the current language, for
    recognising one inside a text. Empty for a language whose endings nobody
    has written down — the text then reads as it was written."""
    from common.i18n import get_locale

    return _ORDINAL_SUFFIXES.get(get_locale(), ())


@cache
def _ordinal_affix_en(value: int) -> tuple[str, str]:
    suffix = 'th'
    if not 11 <= value <= 13:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(value % 10, suffix)
    return '', suffix


@cache
def _ordinal_affix_fr(value: int) -> tuple[str, str]:
    return '', 'er' if value == 1 else 'e'


def ordinal_integer(value: int) -> str:
    """The ordinal of *value*, its ending raised — '1st', '1er', '8e'."""
    from common.i18n import get_locale, _

    locale = get_locale()
    affix_fn: Callable[[int], tuple[str, str]]
    match locale:
        case 'en':
            affix_fn = _ordinal_affix_en
        case 'fr':
            affix_fn = _ordinal_affix_fr
        case _:
            raise NotImplementedError(f'no ordinal affix function for locale {locale}')
    prefix, suffix = affix_fn(value)
    return _('{prefix}{int_value}<sup>{suffix}</sup>').format(
        prefix=prefix, int_value=value, suffix=suffix
    )
