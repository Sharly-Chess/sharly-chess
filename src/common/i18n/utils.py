from string import capwords

from babel import Locale


def locale_flag_url(locale: str):
    """Returns the uri of a locale to the image of its flag."""
    return f'/static/images/locales/{locale}.svg'


def locale_localized_name(locale: str) -> str:
    """Returns the locale in its own language."""
    return capwords(str(Locale.parse(locale).get_display_name()))
