from functools import cache
from pathlib import Path
from typing import Self

from common import BASE_DIR
from plugins import PLUGINS_DIR


class Domain:
    """A class to represent i18n domains (core and plugins with i18n support, name None is for the core of the app)."""

    core_name: str = 'messages'
    core_locale_dir: Path = BASE_DIR / 'locale'

    def __init__(
        self,
        id_: str | None = None,
    ):
        self.id: str | None = id_
        self.name: str = self.id or self.core_name
        self.locale_dir: Path = self._get_domain_locale_dir(self.id)
        self.config_file: Path = self.locale_dir / 'babel.cfg'
        self.pot_file: Path = self.locale_dir / f'{self.name}.pot'

    @property
    def is_core(self) -> bool:
        return self.name == self.core_name

    @classmethod
    def _get_domain_locale_dir(
        cls,
        name: str | None,
    ) -> Path:
        return cls.core_locale_dir if name is None else PLUGINS_DIR / name / 'locale'

    @classmethod
    @cache
    def get_domains(cls) -> list[Self]:
        return [
            cls(),
        ] + [
            cls(plugin_dir.name)
            for plugin_dir in PLUGINS_DIR.glob('*')
            if cls._get_domain_locale_dir(plugin_dir.name).is_dir()
        ]

    def locale_lc_messages_dir(
        self,
        locale: str,
    ) -> Path:
        return self.locale_dir / locale / 'LC_MESSAGES'

    def locale_po_file(
        self,
        locale: str,
    ) -> Path:
        return self.locale_lc_messages_dir(locale) / f'{self.name}.po'

    def locale_mo_file(
        self,
        locale: str,
    ) -> Path:
        return self.locale_po_file(locale).with_suffix('.mo')
