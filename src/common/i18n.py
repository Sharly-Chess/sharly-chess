import gettext as gettext_lib
import sys
import threading
from gettext import GNUTranslations
from logging import Logger
from pathlib import Path
from string import capwords

from babel import Locale

from common import BASE_DIR, DEVEL_ENV
from common.logger import get_logger

logger: Logger = get_logger()

_i18n_script = Path(sys.argv[0]).name in [
    'i18n_update.py',
    'i18n_translate.py',
]

# The default locale used when no default locale is set in the configuration file.
DEFAULT_LOCALE: str = 'en'
logger.debug('Default locale: %s', DEFAULT_LOCALE)

""" The directory where to find the i18n files. """
_locale_dir: Path = BASE_DIR / 'locale'
logger.debug('Locale folder: %s', _locale_dir)


""" Build a dict of all the translations with the available locales retrieved from the filesystem. """
locales: list[str] = []
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
                if DEVEL_ENV and not _i18n_script:
                    # Check that the MO files are up-to-date.
                    po_file: Path = mo_file.with_suffix('.po')
                    if not po_file.is_file():
                        logger.critical('PO file [%s] not found, exiting.', po_file)
                        sys.exit(1)
                    if mo_file.lstat().st_mtime < po_file.lstat().st_mtime:
                        logger.warning('MO file [%s] is out of date.', mo_file)
            except Exception as ex:
                logger.critical('Could not load locale [%s]: %s.', locale_name, ex)
                sys.exit(1)
        else:
            if not _i18n_script:
                logger.critical(
                    'Invalid locale [%s] (MO file [%s] not found), exiting.',
                    l_entry.name,
                    mo_file,
                )
                sys.exit()


# Considering the case when no translation is available is needed
# when the compilation of the PO files failed and no MO files are available.
if not locales:
    if not _i18n_script:
        if DEVEL_ENV:
            logger.critical('Please run i18n_update.py (no locale found), exiting.')
        else:
            logger.critical('No locale found, exiting.')
        sys.exit(1)
    DEFAULT_LOCALE = ''
    # locales are built on the PO files found if no MO files found
    logger.warning('No MO files founds, loading locales from PO files...')
    for l_entry in _locale_dir.iterdir():
        if l_entry.is_dir():
            po_file: Path = l_entry / 'LC_MESSAGES' / 'messages.po'
            if po_file.is_file():
                locales.append(l_entry.name)
    if not locales:
        logger.critical('No PO files found, exiting.')
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
