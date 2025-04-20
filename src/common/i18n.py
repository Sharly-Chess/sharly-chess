import gettext as gettext_lib
import sys
import threading
from gettext import GNUTranslations
from logging import Logger
from pathlib import Path
from string import capwords

from babel import Locale

from common import BASE_DIR, DEVEL_ENV
from common.exception import PapiWebException
from common.logger import get_logger
from scripts.i18n.i18n_babel import BabelWrapper

logger: Logger = get_logger()

_i18n_script = Path(sys.argv[0]).name in [
    'i18n_check.py',
    'i18n_translate.py',
]

# The default locale used when no default locale is set in the configuration file.
DEFAULT_LOCALE: str = 'en'
logger.debug('Default locale: %s', DEFAULT_LOCALE)

# The directory where to find the i18n files.
_locale_dir: Path = BASE_DIR / 'locale'
logger.debug('Locale folder: %s', _locale_dir)

# Build a dict of all the translations with the available locales retrieved from the filesystem.
locales: list[str] = []
for l_entry in _locale_dir.iterdir():
    if l_entry.is_dir():
        mo_file: Path = l_entry / 'LC_MESSAGES' / 'messages.mo'
        if mo_file.is_file():
            locales.append(l_entry.name)
        elif _i18n_script:
            # locales are built on the PO files found if no MO files found
            po_file: Path = l_entry / 'LC_MESSAGES' / 'messages.po'
            if po_file.is_file():
                locales.append(l_entry.name)
        else:
            raise PapiWebException(
                f'Invalid locale [{l_entry.name}] (MO file [{mo_file}] not found), exiting.'
            )

# For developers only, look if the i18n strings have changed to refresh the MO files if needed
if DEVEL_ENV and not _i18n_script:
    BabelWrapper.refresh_i18n_files(locales, verbose=False)

# Now load the translations.
_all_translations: dict[str, GNUTranslations] = {}
for loc in locales:
    try:
        _all_translations[loc] = gettext_lib.translation(
            'messages',
            _locale_dir,
            [
                loc,
            ],
        )
    except Exception as ex:
        raise PapiWebException(f'Could not load locale [{loc}]: {ex}.')

logger.debug('Locales found: %s', ', '.join(locales))

# The translators (assigned to the locales).
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
translators |= {
    locale: [
        {
            'github_user': None,
            'name': 'Unknown',
        },
    ]
    for locale in locales
    if locale not in translators
}

# Initialize the current thread with the default locale.
_thread_local_data = threading.local()


def get_locale() -> str:
    """Returns the locale of the current thread."""
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
    """Returns the uri of a locale to the image of its flag."""
    return f'/static/images/locales/{locale}.svg'


def locale_localized_name(locale: str) -> str:
    """Returns the locale in its own language."""
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
