from pathlib import Path

import common
from common.i18n import plugin_gettext, plugin_ngettext
from plugins import PLUGINS_DIR

PLUGIN_NAME: str = 'ffe'
PLUGIN_DIR: Path = PLUGINS_DIR / PLUGIN_NAME
TMP_DIR: Path = common.TMP_DIR / PLUGIN_NAME
TMP_DIR.mkdir(parents=True, exist_ok=True)


def gettext(message: str, locale: str | None = None):
    return plugin_gettext(PLUGIN_NAME, message, locale)


def _(message: str, locale: str | None = None):
    return gettext(message, locale)


def ngettext(singular: str, plural: str, n: int, locale: str | None = None):
    return plugin_ngettext(PLUGIN_NAME, singular, plural, n, locale)
