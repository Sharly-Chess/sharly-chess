import re
import time
from datetime import datetime
from functools import cached_property
from logging import Logger
from pathlib import Path

from common import BASE_DIR, TMP_DIR
from common.i18n.babel_wrapper import BabelDomainWrapper
from common.i18n.domains import Domain
from common.i18n.locale_info import DomainLocaleInfo
from common.i18n.translators import Translator
from common.i18n.utils import locale_flag_url, locale_localized_name
from common.logger import get_logger
from utils.file import text_files_fingerprint, text_file_fingerprint

logger: Logger = get_logger()


class BabelDomainUpdater(BabelDomainWrapper):
    """A utility class to update translations for a plugin (or the core)."""

    def __init__(
        self,
        domain_id: str | None,
        locales: list[str],
        default_locale: str,
    ):
        super().__init__(domain_id)
        self.locales: list[str] = locales
        self.tmp_dir: Path = TMP_DIR / 'i18n' / self.name
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.domain_locale_infos: dict[str, DomainLocaleInfo] = {
            locale: DomainLocaleInfo(self.id, locale, default_locale)
            for locale in self.locales
        }
        self.default_locale: str = default_locale

    def update(
        self,
        clean: bool,
    ):
        """Update all the files that need to updated (POT, PO, MO), and check the translations."""
        logger.info('Domain [%s]: updating i18n strings...', self.name)
        if clean:
            self.pot_file.unlink(missing_ok=True)
            for domain_locale_info in self.domain_locale_infos.values():
                domain_locale_info.mo_file.unlink(missing_ok=True)
        logger.debug(
            'Domain [%s]: checking if i18n source files have been updated...', self.name
        )
        old_sources_fingerprint: bytes = self.get_sources_fingerprint_for_pot()
        new_sources_fingerprint: bytes = text_files_fingerprint(self.sources)
        build_pot: bool = False
        if not self.pot_file.exists():
            build_pot = True
            logger.info(
                'Domain [%s]: POT file not found, extracting i18n strings...', self.name
            )
        elif old_sources_fingerprint != new_sources_fingerprint:
            build_pot = True
            logger.info(
                'Domain [%s]: source files have changed, extracting i18n strings...',
                self.name,
            )
        else:
            logger.debug(
                'Domain [%s]: source files unchanged, no need to extract i18n strings.',
                self.name,
            )
        if build_pot:
            self.extract_i18n_strings()
            logger.debug('Domain [%s]: wrote POT file.', self.name)
            self.store_sources_fingerprint_for_pot()
        for locale, locale_info in self.domain_locale_infos.items():
            po_file: Path = self.locale_po_file(locale)
            build_po: bool = False
            if not po_file.exists():
                build_po = True
                logger.info(
                    'Domain [%s]: PO file not found for locale [%s], generating from POT file...',
                    self.name,
                    locale,
                )
            elif text_file_fingerprint(
                self.pot_file
            ) != self.get_pot_fingerprint_for_po(locale):
                build_po = True
                logger.info(
                    'Domain [%s]: POT file has changed for locale [%s], updating PO file...',
                    self.name,
                    locale,
                )
            elif text_file_fingerprint(po_file) != self.get_po_fingerprint_for_pot(
                locale
            ):
                build_po = True
                logger.info(
                    'Domain [%s]: PO file has changed for locale [%s], updating...',
                    self.name,
                    locale,
                )
            else:
                logger.debug(
                    'Domain [%s]: POT file unchanged for locale [%s], no need to update the PO file...',
                    self.name,
                    locale,
                )
            if build_po:
                self.update_po_file(locale)
                logger.info('Domain [%s]: wrote PO file.', self.name)
                self.store_pot_fingerprint_for_po(locale)
                self.store_po_fingerprint_for_pot(locale)
            logger.debug(
                'Domain [%s]: checking the translations for locale [%s]...',
                self.name,
                locale,
            )
            po_errors: bool = locale_info.control()
            locale_info.print_summary()
            mo_file: Path = self.locale_mo_file(locale)
            old_po_for_mo_fingerprint: bytes = self.get_po_fingerprint_for_mo(locale)
            po_fingerprint: bytes = text_file_fingerprint(po_file)
            build_mo: bool = False
            if not mo_file.exists():
                build_mo = True
                logger.info(
                    'Domain [%s]: MO file not found for locale [%s], generating from PO file...',
                    self.name,
                    locale,
                )
            elif po_fingerprint != old_po_for_mo_fingerprint:
                build_mo = True
                logger.info(
                    'Domain [%s]: PO file has changed since last MO file generation for locale [%s], updating MO file...',
                    self.name,
                    locale,
                )
            elif po_errors:
                build_mo = True
                logger.info(
                    'Domain [%s]: errors found for locale [%s], rebuilding MO file...',
                    self.name,
                    locale,
                )
            else:
                logger.debug(
                    'Domain [%s]: PO file unchanged for locale [%s], no need to update the MO file...',
                    self.name,
                    locale,
                )
            if build_mo:
                self.store_po_for_mo_fingerprint(locale)
                self.update_mo_file(locale)
                logger.info('Domain [%s]: wrote MO file.', self.name)
        for locale_info in self.domain_locale_infos.values():
            if locale_info.error_messages:
                logger.error(
                    'Domain [%s]: translations are not valid for some locales.',
                    self.name,
                )
                return False
        perfect_locales: list[str] = [
            'fr',
        ]
        other_locales: list[str] = [
            locale
            for locale in self.locales
            if locale not in [self.default_locale] + perfect_locales
        ]
        for locale_info in self.domain_locale_infos.values():
            if locale_info.empty_mandatory_messages:
                logger.error(
                    'Domain [%s]: mandatory translations are missing for some locales.',
                    self.name,
                )
                return False
        for locale in perfect_locales:
            if self.domain_locale_infos[locale].empty_optional_messages:
                logger.error(
                    'Domain [%s]: optional translations are missing for some locales.',
                    self.name,
                )
                return False
        for locale in other_locales:
            if self.domain_locale_infos[locale].empty_optional_messages:
                logger.warning(
                    'Domain [%s]: optional translations are missing for some locales.',
                    self.name,
                )
        for locale in perfect_locales:
            if self.domain_locale_infos[locale].flagged_messages:
                logger.error(
                    'Domain [%s]: translations are flagged for some locales.', self.name
                )
                return False
        for locale in other_locales:
            if self.domain_locale_infos[locale].flagged_messages:
                logger.warning(
                    'Domain [%s]: translations are flagged for some locales.', self.name
                )
        logger.info('Domain [%s]: translations OK.', self.name)
        return True

    def sources_for_pot_fingerprint_file(self) -> Path:
        """Returns the path of the file used to store the fingerprint of the source files."""
        return self.tmp_dir / f'{self.name}-src-pot.fp'

    def get_sources_fingerprint_for_pot(self) -> bytes:
        """Returns the fingerprint of the source files stored to disk."""
        try:
            with open(self.sources_for_pot_fingerprint_file(), 'rb') as f:
                return f.read()
        except FileNotFoundError:
            return bytes()

    def store_sources_fingerprint_for_pot(
        self,
    ):
        """Stores the fingerprint of the sources files."""
        with open(self.sources_for_pot_fingerprint_file(), 'wb') as f:
            return f.write(text_files_fingerprint(self.sources))

    @cached_property
    def sources(self):
        """Returns the list of the source files."""
        pattern_found: bool = False
        files: list[Path] = []
        with open(self.config_file, 'r') as f:
            # looking for patterns in the Babel configuration file
            for line in f:
                if matches := re.match(r'\[\w+: *(.*)]', line):
                    pattern_found = True
                    files += BASE_DIR.glob(matches.group(1))
        if not pattern_found:
            raise FileNotFoundError(
                f'Domain {self.name}: no file pattern found in [{self.config_file}].'
            )
        if not files:
            raise FileNotFoundError(f'Domain {self.name}: No source file found.')
        return files

    def pot_for_po_fingerprint_file(
        self,
        locale: str,
    ) -> Path:
        """Returns the path of the file used to store the fingerprint of the POT file used to update a PO file."""
        return self.tmp_dir / f'{self.name}-{locale}-pot-po.fp'

    def get_pot_fingerprint_for_po(
        self,
        locale: str,
    ) -> bytes:
        """Returns the fingerprint stored to disk of the POT file used tu update a PO file."""
        try:
            with open(self.pot_for_po_fingerprint_file(locale), 'rb') as f:
                return f.read()
        except FileNotFoundError:
            return bytes()

    def store_pot_fingerprint_for_po(
        self,
        locale: str,
    ):
        """Stores the fingerprint of the POT file used to update a PO file."""
        with open(self.pot_for_po_fingerprint_file(locale), 'wb') as f:
            return f.write(text_file_fingerprint(self.pot_file))

    def po_for_pot_fingerprint_file(
        self,
        locale: str,
    ) -> Path:
        """Returns the path of the file used to store the fingerprint of the PO file used to generate a MO file."""
        return self.tmp_dir / f'{self.name}-{locale}-po-pot.fp'

    def get_po_fingerprint_for_pot(
        self,
        locale: str,
    ) -> bytes:
        """Returns the fingerprint stored to disk of the PO file used to generate a MO file."""
        try:
            with open(self.po_for_pot_fingerprint_file(locale), 'rb') as f:
                return f.read()
        except FileNotFoundError:
            return bytes()

    def store_po_fingerprint_for_pot(
        self,
        locale: str,
    ):
        """Stores the fingerprint of the PO file used to generate a MO file."""
        with open(self.po_for_pot_fingerprint_file(locale), 'wb') as f:
            return f.write(text_file_fingerprint(self.locale_po_file(locale)))

    def po_for_mo_fingerprint_file(
        self,
        locale: str,
    ) -> Path:
        """Returns the path of the file used to store the fingerprint of the PO file used to generate a MO file."""
        return self.tmp_dir / f'{self.name}-{locale}-po-mo.fp'

    def get_po_fingerprint_for_mo(
        self,
        locale: str,
    ) -> bytes:
        """Returns the fingerprint stored to disk of the PO file used to generate a MO file."""
        try:
            with open(self.po_for_mo_fingerprint_file(locale), 'rb') as f:
                return f.read()
        except FileNotFoundError:
            return bytes()

    def store_po_for_mo_fingerprint(
        self,
        locale: str,
    ):
        """Stores the fingerprint of the PO file used to generate a MO file."""
        with open(self.po_for_mo_fingerprint_file(locale), 'wb') as f:
            return f.write(text_file_fingerprint(self.locale_po_file(locale)))

    def create_absent_mo_files(self):
        """Creates the MO files when not found (used when first pulling the repository and for testing on GitHub)."""
        for locale, locale_info in self.domain_locale_infos.items():
            mo_file: Path = self.locale_mo_file(locale)
            if not mo_file.exists():
                logger.info(
                    'Domain [%s]: MO file not found for locale [%s], generating from PO file...',
                    self.name,
                    locale,
                )
                self.update_mo_file(locale)
                logger.info('Domain [%s]: wrote MO file.', self.name)
                self.store_po_for_mo_fingerprint(locale)

    def update_mo_files(
        self,
    ):
        """Only update the MO files if the PO files have changed."""
        for locale, locale_info in self.domain_locale_infos.items():
            po_file: Path = self.locale_po_file(locale)
            mo_file: Path = self.locale_mo_file(locale)
            old_po_for_mo_fingerprint: bytes = self.get_po_fingerprint_for_mo(locale)
            po_fingerprint: bytes = text_file_fingerprint(po_file)
            build_mo: bool = False
            if not mo_file.exists():
                build_mo = True
                logger.info(
                    'Domain [%s]: MO file not found for locale [%s], generating from PO file...',
                    self.name,
                    locale,
                )
            elif po_fingerprint != old_po_for_mo_fingerprint:
                build_mo = True
                logger.info(
                    'Domain [%s]: PO file has changed since last MO file generation for locale [%s], updating MO file...',
                    self.name,
                    locale,
                )
            else:
                logger.debug(
                    'Domain [%s]: PO file unchanged for locale [%s], no need to update the MO file...',
                    self.name,
                    locale,
                )
            if build_mo:
                self.store_po_for_mo_fingerprint(locale)
                self.update_mo_file(locale)
                logger.info('Wrote MO file.')


class BabelUpdater:
    """A utility class to update translations."""

    def __init__(
        self,
        domains: list[Domain],
        translators: dict[str, list[Translator]],
        default_locale: str,
    ):
        self.translators: dict[str, list[Translator]] = translators
        self.babel_domain_updaters: list[BabelDomainUpdater] = [
            BabelDomainUpdater(domain.id, self.locales, default_locale)
            for domain in domains
        ]

    @property
    def locales(self) -> list[str]:
        return list(self.translators.keys())

    def update(
        self,
        clean: bool = False,
        generate_doc: bool = False,
    ):
        """For (the core and) all the plugins, update all the files that need to updated (POT, PO, MO), and check the translations."""
        ok: bool = all(
            [
                babel_domain_updater.update(clean=clean)
                for babel_domain_updater in self.babel_domain_updaters
            ]
        )
        if ok and generate_doc:
            self.write_markdown()
        return ok

    def create_absent_mo_files(self):
        """For all the domains, creates the MO files when not found
        (used when first pulling the repository and for testing on GitHub)."""
        for babel_plugin_updater in self.babel_domain_updaters:
            babel_plugin_updater.create_absent_mo_files()

    def update_mo_files(
        self,
    ):
        """ ""For all the domains, only update the MO files if the PO files have changed."""
        for babel_domain_updater in self.babel_domain_updaters:
            babel_domain_updater.update_mo_files()

    def write_markdown(self):
        """For (the core and) all the plugins, update all the files that need to updated (POT, PO, MO), and check the translations."""
        doc_file: Path = BASE_DIR / 'docs' / 'technical-appendices' / 'i18n.md'
        start_lines: list[str] = []
        end_lines: list[str] = []
        with open(doc_file, 'rt', encoding='utf-8') as f:
            start_comment: str = '<!-- DO NOT EDIT! (START) -->'
            start_comment_found: bool = False
            for line in f:
                if line.startswith(start_comment):
                    start_comment_found = True
                    break
                start_lines.append(line)
            if not start_comment_found:
                logger.error(
                    f'Could not edit [{doc_file}] (comment [{start_comment}] not found).'
                )
                return
            end_comment: str = '<!-- DO NOT EDIT! (END) -->'
            end_comment_found: bool = False
            for line in f:
                if end_comment_found:
                    end_lines.append(line)
                if line.startswith(end_comment):
                    end_comment_found = True
            if not end_comment_found:
                logger.error(
                    f'Could not edit [{doc_file}] (comment [{end_comment}] not found).'
                )
                return
        flags: list[str] = list(
            {
                flag
                for babel_domain_updater in self.babel_domain_updaters
                for locale, locale_info in babel_domain_updater.domain_locale_infos.items()
                for flag in locale_info.flagged_messages
            }
        )
        with open(doc_file, 'w', encoding='utf-8') as f:
            for line in (
                start_lines
                + [
                    f'{start_comment}\n',
                ]
                + [
                    f'Last update: {datetime.strftime(datetime.fromtimestamp(time.time()), "%Y-%m-%d %H:%M")}\n\n'
                ]
                + [
                    self.translators_markdown_text(),
                    self.by_locale_markdown_text(flags),
                    self.by_domain_markdown_text(flags),
                ]
                + [
                    f'{end_comment}\n',
                ]
                + end_lines
            ):
                f.write(line)
        logger.info('Wrote [%s].', doc_file)

    def translators_markdown_text(
        self,
    ) -> str:
        headers: list[str] = [
            'Locale',
            'Translators',
        ]
        lines: list[str] = [
            '## Translators\n\n| ' + ' | '.join(headers) + ' |',
            '|--' + ('|--' * (len(headers) - 1)) + '|',
        ]
        for locale in self.locales:
            lines.append(
                f'| <img src="../../src/web{
                    locale_flag_url(locale)
                }" style="height: 1em;"/>&nbsp;``{locale}``&nbsp;{
                    locale_localized_name(locale)
                } | {
                    ", ".join(
                        translator.markdown for translator in self.translators[locale]
                    )
                } |'
            )
        return '\n'.join(lines) + '\n\n'

    def by_locale_markdown_text(
        self,
        flags: list[str],
    ) -> str:
        lines: list[str] = ['## Translations by locale\n']
        for locale in self.locales:
            lines.append(
                f'### <img src="../../src/web{locale_flag_url(locale)}" style="height: 1em;"/>&nbsp;``{locale}``&nbsp;{locale_localized_name(locale)}\n'
            )
            lines += self.markdown_header_lines(
                column1_locale=False,
                domain=None,
                flags=flags,
            )
            for babel_domain_updater in self.babel_domain_updaters:
                domain_locale_info: DomainLocaleInfo = (
                    babel_domain_updater.domain_locale_infos[locale]
                )
                lines.append(
                    self.markdown_line(
                        column1_locale=False,
                        locale=locale,
                        domain=babel_domain_updater,
                        flags=flags,
                        messages_count=len(domain_locale_info.messages),
                        empty_optional_messages_count=len(
                            domain_locale_info.empty_optional_messages
                        ),
                        empty_mandatory_messages_count=len(
                            domain_locale_info.empty_mandatory_messages
                        ),
                        flagged_messages_count={
                            flag: len(domain_locale_info.flagged_messages.get(flag, []))
                            for flag in flags
                        },
                    )
                )
            lines.append(
                self.markdown_line(
                    column1_locale=False,
                    locale=locale,
                    domain=None,
                    flags=flags,
                    messages_count=sum(
                        len(babel_domain_updater.domain_locale_infos[locale].messages)
                        for babel_domain_updater in self.babel_domain_updaters
                    ),
                    empty_optional_messages_count=sum(
                        len(
                            babel_domain_updater.domain_locale_infos[
                                locale
                            ].empty_optional_messages
                        )
                        for babel_domain_updater in self.babel_domain_updaters
                    ),
                    empty_mandatory_messages_count=sum(
                        len(
                            babel_domain_updater.domain_locale_infos[
                                locale
                            ].empty_mandatory_messages
                        )
                        for babel_domain_updater in self.babel_domain_updaters
                    ),
                    flagged_messages_count={
                        flag: sum(
                            len(
                                babel_domain_updater.domain_locale_infos[
                                    locale
                                ].flagged_messages.get(flag, [])
                            )
                            for babel_domain_updater in self.babel_domain_updaters
                        )
                        for flag in flags
                    },
                )
            )
        return '\n'.join(lines) + '\n\n'

    def by_domain_markdown_text(
        self,
        flags: list[str],
    ) -> str:
        lines: list[str] = ['## Translations by domain\n']
        lines += self.domain_markdown_lines(
            domain=None,
            flags=flags,
            messages_count_by_locale={
                locale: sum(
                    len(babel_domain_updater.domain_locale_infos[locale].messages)
                    for babel_domain_updater in self.babel_domain_updaters
                )
                for locale in self.locales
            },
            empty_optional_messages_count_by_locale={
                locale: sum(
                    len(
                        babel_domain_updater.domain_locale_infos[
                            locale
                        ].empty_optional_messages
                    )
                    for babel_domain_updater in self.babel_domain_updaters
                )
                for locale in self.locales
            },
            empty_mandatory_messages_count_by_locale={
                locale: sum(
                    len(
                        babel_domain_updater.domain_locale_infos[
                            locale
                        ].empty_mandatory_messages
                    )
                    for babel_domain_updater in self.babel_domain_updaters
                )
                for locale in self.locales
            },
            flagged_messages_count_by_locale={
                locale: {
                    flag: sum(
                        len(
                            babel_domain_updater.domain_locale_infos[
                                locale
                            ].flagged_messages.get(flag, [])
                        )
                        for babel_domain_updater in self.babel_domain_updaters
                    )
                    for flag in flags
                }
                for locale in self.locales
            },
        )
        for babel_domain_updater in self.babel_domain_updaters:
            lines += self.domain_markdown_lines(
                domain=babel_domain_updater,
                flags=flags,
                messages_count_by_locale={
                    locale: len(locale_info.messages)
                    for locale, locale_info in babel_domain_updater.domain_locale_infos.items()
                },
                empty_optional_messages_count_by_locale={
                    locale: len(locale_info.empty_optional_messages)
                    for locale, locale_info in babel_domain_updater.domain_locale_infos.items()
                },
                empty_mandatory_messages_count_by_locale={
                    locale: len(locale_info.empty_mandatory_messages)
                    for locale, locale_info in babel_domain_updater.domain_locale_infos.items()
                },
                flagged_messages_count_by_locale={
                    locale: {
                        flag: len(locale_info.flagged_messages.get(flag, []))
                        for flag in flags
                    }
                    for locale, locale_info in babel_domain_updater.domain_locale_infos.items()
                },
            )
        return '\n'.join(lines) + '\n\n'

    def domain_markdown_lines(
        self,
        domain: Domain | None,
        flags: list[str],
        messages_count_by_locale: dict[str, int],
        empty_optional_messages_count_by_locale: dict[str, int],
        empty_mandatory_messages_count_by_locale: dict[str, int],
        flagged_messages_count_by_locale: dict[str, dict[str, int]],
    ) -> list[str]:
        title: str
        if not domain:
            title = 'Core and plugins'
        elif domain.is_core:
            title = 'Core'
        else:
            title = f'Plugin {domain.name}'
        return (
            [f'### {title}\n']
            + self.markdown_header_lines(
                column1_locale=True,
                domain=domain,
                flags=flags,
            )
            + [
                self.markdown_line(
                    column1_locale=True,
                    locale=locale,
                    domain=domain,
                    flags=flags,
                    messages_count=messages_count_by_locale[locale],
                    empty_optional_messages_count=empty_optional_messages_count_by_locale[
                        locale
                    ],
                    empty_mandatory_messages_count=empty_mandatory_messages_count_by_locale[
                        locale
                    ],
                    flagged_messages_count=flagged_messages_count_by_locale[locale],
                )
                for locale in self.locales
            ]
            + [
                '',
            ]
        )

    @staticmethod
    def markdown_header_lines(
        column1_locale: bool,
        domain: Domain | None,
        flags: list[str],
    ) -> list[str]:
        headers: list[str] = [
            'Locale' if column1_locale else 'Domain',
            'Messages',
            'Empty',
            'Empty mandatory',
        ] + [f'[{flag}]' for flag in flags]
        if domain:
            headers += [
                'PO file',
            ]
        return [
            '| ' + ' | '.join(headers) + ' |',
            '|--' + ('|:--:' * (len(headers) - 1)) + '|',
        ]

    @staticmethod
    def markdown_line(
        column1_locale: bool,
        locale: str,
        domain: Domain | None,
        flags: list[str],
        messages_count: int,
        empty_optional_messages_count: int,
        empty_mandatory_messages_count: int,
        flagged_messages_count: dict[str, int],
    ) -> str:
        column1: str
        if column1_locale:
            column1 = f'<img src="../../src/web{locale_flag_url(locale)}" style="height: 1em;"/>&nbsp;``{locale}``&nbsp;{locale_localized_name(locale)}'
        elif domain:
            column1 = 'Core' if domain.is_core else f'Plugin `{domain.name}`'
        else:
            column1 = 'Core and plugins'
        line: str = f'| {column1} '
        line += f'| {messages_count if messages_count else "-"} '
        line += f'| {empty_optional_messages_count if empty_optional_messages_count else "-"} '
        line += f'| {empty_mandatory_messages_count if empty_mandatory_messages_count else "-"} '
        for flag in flags:
            line += f'| {flagged_messages_count[flag] if flagged_messages_count[flag] else "-"} '
        if domain:
            po_file: Path = domain.locale_po_file(locale)
            line += f'| [{po_file.name}](../..{"/".join(d.name for d in reversed(po_file.relative_to(BASE_DIR).parents))}/{po_file.name}) '
        line += '|'
        return line
