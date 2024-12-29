import gettext
import threading
from collections import namedtuple
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
locale_dir = Path('locale')

""" The available locales, retrieved from the filesystem. """
locales: list[str] = [
    entry.name for entry in locale_dir.iterdir() if entry.is_dir()
]
assert default_locale in locales

""" Initialize the current thread with the default locale. """
_thread_local_data = threading.local()


def get_locale() -> str | None:
    try:
        return _thread_local_data.locale
    except AttributeError:
        return None


def get_locale_or_default() -> str:
    return get_locale() or default_locale


def set_locale(locale: str) -> bool:
    """ Sets the locale for the current thread, returns True if the given locale is recognized. """
    if locale in locales:
        _thread_local_data.locale = locale
        logger.debug(_('Locale set to [{locale}].').format(locale=locale))
        return True
    else:
        logger.warning(_('Unknown locale [{locale}].').format(locale=locale))
        return False


""" Build a dict with the information of the available locales to help in changing the locale used. """
LocaleInfo = namedtuple('LocaleInfo', ['name', 'flag', ])
locale_infos: dict[str, LocaleInfo] = {
    locale: (
        capwords(Locale.parse(locale).get_display_name()),  # the translated name
        f'/static/images/locales/{locale}.svg',  # the URL of the corresponding flag image
    ) for locale in locales
}

""" Build a dict of all the translations. """
_all_translations: dict[str, GNUTranslations] = {
    locale: gettext.translation('messages', locale_dir, [locale]) for locale in locales
}

def gettext_for_locale(message: str, locale: str):
    """ Returns the translation of a string for a given locale. """
    return _all_translations[locale].gettext(message)


def gettext(message: str):
    """ Overrides the gettext.gettext() function to use the locale of the current thread. """
    return gettext_for_locale(message, get_locale_or_default())


def _(message: str):
    """ An alias for gettext(). """
    return gettext(message)


def ngettext_for_locale(singular: str, plural: str, n: int, locale: str):
    """ Returns the translation of a string for a given locale. """
    return _all_translations[locale].ngettext(singular, plural, n)


def ngettext(singular: str, plural: str, n: int):
    """ Overrides the gettext.ngettext() function to use the locale of the current thread. """
    return ngettext_for_locale(singular, plural, n, get_locale_or_default())
