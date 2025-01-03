import gettext
import sys
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
_locale_dir: Path = (
        (Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]) / "locale")

""" The available locales, retrieved from the filesystem. """
locales: list[str] = [
    entry.name for entry in _locale_dir.iterdir()
    if entry.is_dir() and (entry / 'LC_MESSAGES' / 'messages.mo').is_file()
]
assert default_locale in locales

""" The translators (assigned to the trusted locales). """
translators: dict[str, list[dict[str, str | None]]] = {
    'en': [
        {
            'github_user': 'timothyarmes',
            'name': 'Timothy ARMES',
        },
    ],
    'fr': [
        {
            'github_user': 'pascalaubry',
            'name': 'Pascal AUBRY',
        },
        {
            'github_user': 'Amaras',
            'name': 'Sammy PLAT',
        },
    ],
}

""" Trusted locales are the ones with translators assigned. """
trusted_locales: list[str] = list(translators.keys())
untrusted_locales: list[str] = list(set(locales) - set(trusted_locales))

""" Mark the untrusted locales as translated by an IA. """
translators |= {
    locale: {
            'github_user': None,
            'name': 'Opus-MT (IA translation)',
        }
    for locale in locales
    if locale not in trusted_locales
}

""" Initialize the current thread with the default locale. """
_thread_local_data = threading.local()

""" Build a dict of all the translations. """
_all_translations: dict[str, GNUTranslations] = {}
for locale in locales:
    try:
        _all_translations[locale] = gettext.translation('messages', _locale_dir, [locale, ])
    except Exception as ex:
        logger.warning(f'Could not load locale [{locale}]: {ex}')


def _get_locale() -> str:
    try:
        return _thread_local_data.locale
    except AttributeError:
        return default_locale


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


def gettext(message: str, locale: str | None = None):
    """ Overrides the gettext.gettext() function to use the locale of the current thread. """
    return _all_translations[locale or _get_locale()].gettext(message)


def _(message: str, locale: str | None = None):
    """ An alias for gettext(). """
    return gettext(message, locale)


def ngettext(singular: str, plural: str, n: int, locale: str | None = None):
    """ Overrides the gettext.ngettext() function to use the locale of the current thread. """
    return _all_translations[locale or _get_locale()].ngettext(singular, plural, n)
