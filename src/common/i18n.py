import gettext
import threading
from gettext import GNUTranslations
from logging import Logger
from pathlib import Path
from string import capwords

from babel import Locale

from common import get_logger

logger: Logger = get_logger()

""" The default locale used when no default locale is set in the configuration file. """
default_locale: str = 'en'

""" The directory where to find the i18n files. """
_locale_dir = Path('locale')

""" The available locales, retrieved from the filesystem. """
locales: list[str] = [
    entry.name for entry in _locale_dir.iterdir() if entry.is_dir()
]
assert default_locale in locales

""" Initialize the current thread with the default locale. """
_thread_local_data = threading.local()

""" Build a dict of all the translations. """
_all_translations: dict[str, GNUTranslations] = {
    locale: gettext.translation('messages', _locale_dir, [locale, ]) for locale in locales
}


def _get_locale() -> str | None:
    try:
        return _thread_local_data.locale
    except AttributeError:
        return None


def _get_locale_or_default() -> str:
    return _get_locale() or default_locale


def set_locale(locale: str) -> bool:
    """ Sets the locale for the current thread, returns True if the given locale is recognized. """
    if locale in locales:
        _thread_local_data.locale = locale
        logger.debug(_('Locale set to [{locale}].').format(locale=locale))
        return True
    else:
        logger.warning(_('Unknown locale [{locale}].').format(locale=locale))
        return False


def locale_flag_url(locale: str):
    return f'/static/images/locales/{locale}.svg'

def locale_localized_name(locale: str):
    return capwords(Locale.parse(locale).get_display_name())

def gettext_for_locale(message: str, locale: str):
    """ Returns the translation of a string for a given locale. """


def gettext(message: str, locale: str | None = None):
    """ Overrides the gettext.gettext() function to use the locale of the current thread. """
    return _all_translations[locale or _get_locale() or default_locale].gettext(message)


def _(message: str, locale: str | None = None):
    """ An alias for gettext(). """
    return gettext(message, locale)


def ngettext(singular: str, plural: str, n: int, locale: str | None = None):
    """ Overrides the gettext.ngettext() function to use the locale of the current thread. """
    return _all_translations[locale or _get_locale() or default_locale].ngettext(singular, plural, n)
