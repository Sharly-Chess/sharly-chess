from common.i18n import plugin_gettext, plugin_ngettext

PLUGIN_NAME = 'pairing_acceleration'


def gettext(message: str, locale: str | None = None):
    return plugin_gettext(PLUGIN_NAME, message, locale)


def _(message: str, locale: str | None = None):
    return gettext(message, locale)


def ngettext(singular: str, plural: str, n: int, locale: str | None = None):
    return plugin_ngettext(PLUGIN_NAME, singular, plural, n, locale)
