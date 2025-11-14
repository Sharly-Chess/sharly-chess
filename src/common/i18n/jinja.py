import os
import traceback

import common.i18n
from common.i18n import Domain

_domains: list[Domain] = Domain.get_domains()
_filename_pattern: str = os.sep + os.sep.join(['src', 'plugins']) + os.sep
_file_pattern_len: int = len(_filename_pattern)


def get_i18n_domain() -> str:
    global _domains
    for frame_summary in reversed(traceback.extract_stack()):
        if frame_summary.name == 'root':  # the name for Jinja template instructions
            pos: int = frame_summary.filename.rfind(_filename_pattern)
            if pos == -1:
                continue
            relative_path: str = frame_summary.filename[pos + _file_pattern_len :]
            plugin_name: str = relative_path.split(os.sep, 1)[0]
            if plugin_name in _domains:
                return plugin_name
            break
    return Domain.core_name


def gettext(message: str, locale: str | None = None):
    return common.i18n.plugin_gettext(get_i18n_domain(), message, locale)


def _(message: str, locale: str | None = None):
    return gettext(message, locale)


def ngettext(singular: str, plural: str, n: int, locale: str | None = None):
    return common.i18n.plugin_ngettext(get_i18n_domain(), singular, plural, n, locale)
