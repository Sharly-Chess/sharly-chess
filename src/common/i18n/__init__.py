import gettext as gettext_lib
import threading
from gettext import GNUTranslations
from logging import Logger
from pathlib import Path

from common import BASE_DIR, DEVEL_ENV
from common.exception import SharlyChessException
from common.i18n.babel_updaters import BabelUpdater, BabelMOFilesUpdater
from common.i18n.locale_info import LocaleInfo

from common.logger import get_logger

logger: Logger = get_logger()

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
        elif DEVEL_ENV:
            # locales are built on the PO files found if no MO files found
            po_file: Path = l_entry / 'LC_MESSAGES' / 'messages.po'
            if po_file.is_file():
                locales.append(l_entry.name)
        else:
            raise SharlyChessException(
                f'Invalid locale [{l_entry.name}] (MO file [{mo_file}] not found), exiting.'
            )

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

locale_infos: dict[str, LocaleInfo] = {
    locale: LocaleInfo(
        locale, _locale_dir, locale == DEFAULT_LOCALE, translators[locale]
    )
    for locale in locales
}

_auto_update_file: Path = BASE_DIR / 'src' / 'common' / 'i18n' / '.auto-update'

if DEVEL_ENV:
    if _auto_update_file.is_file():
        BabelUpdater(locale_infos, DEFAULT_LOCALE)
    else:
        BabelMOFilesUpdater(locales)


def update_i18n_files():
    """Update all the i18n files if needed (does nothing when .auto-update is found not to do the job twice)."""
    if not _auto_update_file.is_file():
        BabelUpdater(locale_infos, DEFAULT_LOCALE)


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
        raise SharlyChessException(f'Could not load locale [{loc}]: {ex}.')

logger.debug('Locales found: %s', ', '.join(locales))

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
    if hasattr(_thread_local_data, 'locale') and _thread_local_data.locale == locale:
        return True
    if locale in locales:
        _thread_local_data.locale = locale
        logger.debug('Locale set to [%s].', locale)
        return True
    else:
        logger.warning('Unknown locale [%s].', locale)
        return False


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
