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


""" Build a dict of all the translations with the available locales retrieved from the filesystem. """
locales: list[str] = []
_all_translations: dict[str, GNUTranslations] = {}
for l_entry in _locale_dir.iterdir():
    if l_entry.is_dir() and (l_entry / 'LC_MESSAGES' / 'messages.mo').is_file():
        l: str = l_entry.name
        try:
            _all_translations[l] = gettext.translation('messages', _locale_dir, [l, ])
            locales.append(l)
        except Exception as ex:
            logger.warning(f'Could not load locale [{l}]: {ex}')


""" The translators (assigned to the trusted locales). """
translators: dict[str, list[dict[str, str | None]]] = {}


""" Trusted locales are the ones shown to all the users. """
trusted_locales: list[str] = []


""" All the locales that are not trusted, show only when experimental_locales is set in papi-web.ini. """
untrusted_locales: list[str] = []


# Considering the case when no translation is available is needed
# when the compilation of the PO files failed and no MO files are available.
if locales:
    # Check that the default locale is present
    assert default_locale in locales
    """ The translators (assigned to the trusted locales). """
    translators['en'] = [
        {
            'github_user': 'timothyarmes',
            'name': 'Timothy ARMES',
        },
    ]
    translators['fr']= [
        {
            'github_user': 'pascalaubry',
            'name': 'Pascal AUBRY',
        },
        {
            'github_user': 'Amaras',
            'name': 'Sammy PLAT',
        },
    ]
    """ Locales with translators assigned are considered trusted. """
    trusted_locales = list(translators.keys())
    """ Mark the untrusted locales as translated by an IA. """
    translators |= {
        locale: [
            {
                'github_user': None,
                'name': 'AI (Opus-MT)',
            },
        ]
        for locale in locales
        if locale not in trusted_locales
    }
    """ Other as considered untrusted. """
    untrusted_locales = list(set(locales) - set(trusted_locales))
else:
    default_locale = ''


""" Initialize the current thread with the default locale. """
_thread_local_data = threading.local()


def get_locale() -> str:
    try:
        return _thread_local_data.locale
    except AttributeError:
        return default_locale


def set_locale(locale: str) -> bool:
    """ Sets the locale for the current thread, returns True if the given locale is recognized. """
    if locale in locales:
        _thread_local_data.locale = locale
        logger.debug(f'Locale set to [{locale}].')
        return True
    else:
        logger.warning(f'Unknown locale [{locale}].')
        return False


def locale_flag_url(locale: str):
    return f'/static/images/locales/{locale}.svg'


def locale_localized_name(locale: str):
    return capwords(Locale.parse(locale).get_display_name())


def gettext(message: str, locale: str | None = None):
    """ Overrides the gettext.gettext() function to use the locale of the current thread. """
    if locales:
        return _all_translations[locale or get_locale()].gettext(message)
    else:
        return gettext.gettext(message)


def _(message: str, locale: str | None = None):
    """ An alias for gettext(). """
    return gettext(message, locale)


def ngettext(singular: str, plural: str, n: int, locale: str | None = None):
    """ Overrides the gettext.ngettext() function to use the locale of the current thread. """
    if locales:
        return _all_translations[locale or get_locale()].ngettext(singular, plural, n)
    else:
        return gettext.ngettext(singular, plural, n)
