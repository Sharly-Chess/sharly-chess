import re
import time
from datetime import datetime
from functools import cached_property
from logging import Logger
from pathlib import Path

from common import BASE_DIR, TMP_DIR
from common.i18n.utils import locale_flag_url, locale_localized_name
from common.i18n.babel_wrapper import BabelWrapper
from common.i18n.locale_info import LocaleInfo
from common.logger import get_logger
from utils.file import text_files_fingerprint, text_file_fingerprint

logger: Logger = get_logger()


class BabelUpdater(BabelWrapper):
    """Update all the files that need to updated (POT, PO, MO), and check the translations.
    Usage:
    if BabelUpdater().ok:
        ...
    """

    def __init__(
        self,
        locale_infos: dict[str, LocaleInfo],
        default_locale: str,
    ):
        self.tmp_dir: Path = TMP_DIR / 'i18n'
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.locale_infos: dict[str, LocaleInfo] = locale_infos
        self.default_locale: str = default_locale

    def update(
        self,
        generate_doc: bool,
    ):
        logger.debug('Checking if i18n source files have been updated...')
        old_sources_fingerprint: bytes = self.get_sources_fingerprint()
        new_sources_fingerprint: bytes = text_files_fingerprint(self.sources)
        build_pot: bool = False
        if not self.pot_file.exists():
            build_pot = True
            logger.info('POT file not found, extracting i18n strings...')
        elif old_sources_fingerprint != new_sources_fingerprint:
            build_pot = True
            logger.info('Source files have changed, extracting i18n strings...')
        else:
            logger.debug('Source files unchanged, no need to extract i18n strings.')
        if build_pot:
            self.store_sources_fingerprint()
            self.extract_i18n_strings()
            logger.info('Wrote POT file.')
        for locale, locale_info in self.locale_infos.items():
            po_file: Path = self.locale_po_file(locale)
            build_po: bool = False
            if not po_file.exists():
                build_po = True
                logger.info(
                    'PO file not found for locale [%s], generating from POT file...',
                    locale,
                )
            elif text_file_fingerprint(self.pot_file) != self.get_pot_fingerprint(
                locale
            ):
                build_po = True
                logger.info(
                    'POT file has changed for locale [%s], updating PO file...', locale
                )
            elif text_file_fingerprint(po_file) != self.get_po_fingerprint(locale):
                build_po = True
                logger.info('PO file has changed for locale [%s], updating...', locale)
            else:
                logger.debug(
                    'POT file unchanged for locale [%s], no need to update the PO file...',
                    locale,
                )
            if build_po:
                self.update_po_file(locale)
                logger.info('Wrote PO file.')
                self.store_pot_fingerprint(locale)
                self.store_po_fingerprint(locale)
            po_errors: bool = locale_info.control()
            locale_info.print_summary()
            mo_file: Path = self.locale_mo_file(locale)
            old_po_fingerprint: bytes = self.get_po_fingerprint(locale)
            po_fingerprint: bytes = text_file_fingerprint(po_file)
            build_mo: bool = False
            if not mo_file.exists():
                build_mo = True
                logger.info(
                    'MO file not found for locale [%s], generating from PO file...',
                    locale,
                )
            elif po_fingerprint != old_po_fingerprint:
                build_mo = True
                logger.info(
                    'PO file has changed for locale [%s], updating MO file...', locale
                )
            elif po_errors:
                build_mo = True
                logger.info(
                    'Errors found for locale [%s], rebuilding MO file...', locale
                )
            else:
                logger.debug(
                    'PO file unchanged for locale [%s], no need to update the MO file...',
                    locale,
                )
            if build_mo:
                self.store_po_fingerprint(locale)
                self.update_mo_file(locale)
                logger.info('Wrote MO file.')
                if generate_doc:
                    self.write_markdown()
        ok: bool = True
        logger.info('Checking the translations...')
        for locale_info in self.locale_infos.values():
            if locale_info.error_messages:
                logger.error('Translations are not valid for some locales.')
                ok = False
                break
        for locale_info in self.locale_infos.values():
            if locale_info.empty_mandatory_messages:
                logger.error('Mandatory translations are missing for some locales.')
                ok = False
                break
        for locale_info in self.locale_infos.values():
            if not locale_info.default and locale_info.empty_optional_messages:
                logger.warning('Translations are missing for some locales.')
                ok = False
                break
        for locale_info in self.locale_infos.values():
            if locale_info.flagged_messages:
                logger.warning('Translations are flagged for some locales.')
                ok = False
                break
        if ok:
            logger.info('Translations OK.')
        return ok

    def sources_fingerprint_file(self) -> Path:
        """Returns the path of the file used to store the fingerprint of the source files."""
        return self.tmp_dir / 'src-pot.fp'

    def get_sources_fingerprint(self) -> bytes:
        """Returns the fingerprint of the source files stored to disk."""
        try:
            with open(self.sources_fingerprint_file(), 'rb') as f:
                return f.read()
        except FileNotFoundError:
            return bytes()

    def store_sources_fingerprint(
        self,
    ):
        """Stores the fingerprint of the sources files."""
        with open(self.sources_fingerprint_file(), 'wb') as f:
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
            raise FileNotFoundError(f'No file pattern found in [{self.config_file}].')
        if not files:
            raise FileNotFoundError('No source file found.')
        return files

    def pot_fingerprint_file(
        self,
        locale: str,
    ) -> Path:
        """Returns the path of the file used to store the fingerprint of the POT file used to update a PO file."""
        return self.tmp_dir / f'{locale}-pot-po.fp'

    def get_pot_fingerprint(
        self,
        locale: str,
    ) -> bytes:
        """Returns the fingerprint stored to disk of the POT file used tu update a PO file."""
        try:
            with open(self.pot_fingerprint_file(locale), 'rb') as f:
                return f.read()
        except FileNotFoundError:
            return bytes()

    def store_pot_fingerprint(
        self,
        locale: str,
    ):
        """Stores the fingerprint of the POT file used to update a PO file."""
        with open(self.pot_fingerprint_file(locale), 'wb') as f:
            return f.write(text_file_fingerprint(self.pot_file))

    def po_fingerprint_file(
        self,
        locale: str,
    ) -> Path:
        """Returns the path of the file used to store the fingerprint of the PO file used to generate a MO file."""
        return self.tmp_dir / f'{locale}-po-mo.fp'

    def get_po_fingerprint(
        self,
        locale: str,
    ) -> bytes:
        """Returns the fingerprint stored to disk of the PO file used to generate a MO file."""
        try:
            with open(self.po_fingerprint_file(locale), 'rb') as f:
                return f.read()
        except FileNotFoundError:
            return bytes()

    def store_po_fingerprint(
        self,
        locale: str,
    ):
        """Stores the fingerprint of the PO file used to generate a MO file."""
        with open(self.po_fingerprint_file(locale), 'wb') as f:
            return f.write(text_file_fingerprint(self.locale_po_file(locale)))

    def write_markdown(self):
        """Update the i18n doc file with the status of the translations."""
        new_signature, new_lines = self.markdown_variable_part()
        doc_file: Path = BASE_DIR / 'docs' / 'technical-appendices' / 'i18n.md'
        start_lines: list[str] = []
        end_lines: list[str] = []
        with open(doc_file, 'rt', encoding='utf-8') as f:
            start_comment_pattern: re.Pattern = re.compile(
                r'^<!-- DO NOT EDIT! \(START ([^)]+)\) -->'
            )
            start_comment: str = '<!-- DO NOT EDIT! (START {signature}) -->'
            start_comment_found: bool = False
            for line in f:
                if matches := start_comment_pattern.match(line):
                    if new_signature == matches.group(1):
                        logger.info(f'[{doc_file}] unchanged.')
                        return
                    start_comment_found = True
                    break
                start_lines.append(line)
            if not start_comment_found:
                logger.error(
                    f'Could not edit [{doc_file}] (comment [{start_comment.format(signature="signature")}] not found).'
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
        with open(doc_file, 'w', encoding='utf-8') as f:
            for line in (
                start_lines
                + [
                    f'{start_comment.format(signature=new_signature)}\n',
                ]
                + new_lines
                + [
                    f'{end_comment}\n',
                ]
                + end_lines
            ):
                f.write(line)
        logger.info('Wrote [%s].', doc_file)

    def markdown_variable_part(self) -> tuple[str, list[str]]:
        """Returns the variable part of the i18n doc file and a signature and a list of strings."""
        lines: list[str] = []
        flags: set[str] = set()
        for locale in self.locale_infos:
            for flag in sorted(self.locale_infos[locale].flagged_messages.keys()):
                flags.add(flag)
        headers: list[str] = [
            'Locale',
            'Messages',
            'Empty',
            'Empty mandatory',
        ]
        headers += [f'[{flag}]' for flag in flags]
        headers += [
            'PO file',
            'Translators',
        ]
        lines.append('| ' + ' | '.join(headers) + ' |\n')
        lines.append('|--' + ('|:--:' * (len(headers) - 1)) + '|\n')
        locale_signatures: list[str] = []
        for locale, locale_info in self.locale_infos.items():
            locale_signature: str = f'{locale}|{len(locale_info.messages)}|{len(locale_info.empty_optional_messages)}|{len(locale_info.empty_mandatory_messages)}'
            line: str = f'|<img src="../../src/web{locale_flag_url(locale)}" style="height: 1em;"/>&nbsp;``{locale}``&nbsp;{locale_localized_name(locale)} '
            line += f'| {len(locale_info.messages)} '
            line += f'| {len(locale_info.empty_optional_messages)} '
            line += f'| {len(locale_info.empty_mandatory_messages)} '
            for flag in flags:
                line += f'| {len(locale_info.flagged_messages.get(flag, []))} '
                locale_signature += (
                    f'|{len(locale_info.flagged_messages.get(flag, []))}'
                )
            locale_signatures.append(locale_signature)
            line += (
                f'| [{locale_info.po_file.name}]('
                + '/'.join(
                    reversed(
                        [
                            locale_info.po_file.name,
                        ]
                        + [d.name for d in locale_info.po_file.parents[:3]]
                        + [
                            '..',
                        ]
                    )
                )
                + ') '
            )
            translator_strings: list[str] = []
            for translator in locale_info.translators:
                if translator['github_user']:
                    translator_strings.append(
                        f'[{translator["name"]}](https://github.com/{translator["github_user"]})'
                    )
                else:
                    translator_strings.append(translator['name'] or '')
            line += f'| {"<br/>".join(translator_strings)} |\n'
            lines.append(line)
        lines.append(
            f'Last update: {datetime.strftime(datetime.fromtimestamp(time.time()), "%Y-%m-%d %H:%M")}\n'
        )
        return '|'.join(locale_signatures), lines

    def create_absent_mo_files(self):
        """Creates the MO files when not found (used when first pulling the repository and for testing on GitHub)."""
        for locale, locale_info in self.locale_infos.items():
            mo_file: Path = self.locale_mo_file(locale)
            if not mo_file.exists():
                logger.info(
                    'MO file not found for locale [%s], generating from PO file...',
                    locale,
                )
                self.update_mo_file(locale)
                logger.info('Wrote MO file.')
                self.store_po_fingerprint(locale)
