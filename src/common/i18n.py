import gettext as gettext_lib
import sys
import threading
from gettext import GNUTranslations
from logging import Logger
from pathlib import Path
from string import capwords

from babel import Locale

from common import get_logger, BASE_DIR, DEVEL_ENV, EXPERIMENTAL_FEATURES
from common.logger import (
    print_interactive_error,
    print_interactive_warning,
    input_interactive,
)

logger: Logger = get_logger()


""" The default locale used when no default locale is set in the configuration file. """
DEFAULT_LOCALE: str = 'en'


""" The directory where to find the i18n files. """
_locale_dir: Path = BASE_DIR / 'locale'


""" Build a dict of all the translations with the available locales retrieved from the filesystem. """
locales: list[str] = []
LOCALE_ERROR: bool = False
_all_translations: dict[str, GNUTranslations] = {}
for l_entry in _locale_dir.iterdir():
    if l_entry.is_dir():
        mo_file: Path = l_entry / 'LC_MESSAGES' / 'messages.mo'
        if mo_file.is_file():
            locale_name: str = l_entry.name
            try:
                _all_translations[locale_name] = gettext_lib.translation(
                    'messages',
                    _locale_dir,
                    [
                        locale_name,
                    ],
                )
                locales.append(locale_name)
                if DEVEL_ENV:
                    # Check that the MO files are up-to-date.
                    po_file: Path = mo_file.with_suffix('.po')
                    if not po_file.is_file():
                        print_interactive_warning(f'PO file [{po_file}] not found.')
                    elif mo_file.lstat().st_mtime < po_file.lstat().st_mtime:
                        print_interactive_warning(
                            f'MO file [{mo_file}] is out of date.'
                        )
            except Exception as ex:
                print_interactive_error(f'Could not load locale [{locale_name}]: {ex}.')
                LOCALE_ERROR = True
                if not DEVEL_ENV:
                    sys.exit()
        else:
            print_interactive_error(
                f'Invalid locale [{l_entry.name}], MO file [{mo_file}] not found.'
            )
            LOCALE_ERROR = True
            if not DEVEL_ENV:
                sys.exit()


# The translators (assigned to the trusted locales).
translators: dict[str, list[dict[str, str | None]]] = {}


# Trusted locales are the ones shown to all the users.
trusted_locales: list[str] = []


# All the locales that are not trusted, show only when experimental_locales is set in papi-web.ini.
untrusted_locales: list[str] = []


# Considering the case when no translation is available is needed
# when the compilation of the PO files failed and no MO files are available.
if not locales:
    print_interactive_error('No locale found.')
    LOCALE_ERROR = True
    DEFAULT_LOCALE = ''
    if not DEVEL_ENV:
        sys.exit()
elif DEFAULT_LOCALE not in locales:
    print_interactive_error(
        f'Default locale [{DEFAULT_LOCALE}] not found, defaults to [{locales[0]}].'
    )
    LOCALE_ERROR = True
    DEFAULT_LOCALE = locales[0]
    if not DEVEL_ENV:
        sys.exit()

# The translators (assigned to the trusted locales).
translators['en'] = [
    {
        'github_user': 'timothyarmes',
        'name': 'Timothy ARMES',
    },
]
translators['fr'] = [
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
trusted_locales = [locale for locale in translators if locale in locales]

if EXPERIMENTAL_FEATURES:
    # Mark the untrusted locales as translated by an IA.
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
    # Other as considered untrusted.
    untrusted_locales = list(set(locales) - set(trusted_locales))

# Initialize the current thread with the default locale.
_thread_local_data = threading.local()

if LOCALE_ERROR:
    if Path(sys.argv[0]).name != 'i18n_update.py':
        print_interactive_error(
            'Errors were found while loading locales, you should run i18n_update.'
        )
        if (input_interactive('Do you still wish to continue (Y/n)? ') or 'Y') != 'Y':
            sys.exit()


def get_locale() -> str:
    try:
        return _thread_local_data.locale
    except AttributeError:
        return DEFAULT_LOCALE


def set_locale(locale: str) -> bool:
    """Sets the locale for the current thread, returns True if the given locale is recognized."""
    if locale in locales:
        _thread_local_data.locale = locale
        logger.debug('Locale set to [%s].', locale)
        return True
    else:
        logger.warning('Unknown locale [%s].', locale)
        return False


def locale_flag_url(locale: str):
    return f'/static/images/locales/{locale}.svg'


def locale_localized_name(locale: str) -> str:
    return capwords(str(Locale.parse(locale).get_display_name()))


def gettext(message: str, locale: str | None = None):
    """Overrides the gettext.gettext() function to use the locale of the current thread."""
    if locales:
        return _all_translations[locale or get_locale()].gettext(message)
    else:
        return gettext_lib.gettext(message)


def _(message: str, locale: str | None = None):
    """An alias for gettext()."""
    return gettext(message, locale)


def ngettext(singular: str, plural: str, n: int, locale: str | None = None):
    """Overrides the gettext.ngettext() function to use the locale of the current thread."""
    if locales:
        return _all_translations[locale or get_locale()].ngettext(singular, plural, n)
    else:
        return gettext_lib.ngettext(singular, plural, n)
