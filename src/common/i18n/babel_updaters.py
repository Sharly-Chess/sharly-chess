import json
import re
import time
from datetime import datetime
from logging import Logger
from pathlib import Path

from common import BASE_DIR, TMP_DIR
from common.i18n.utils import locale_flag_url, locale_localized_name
from common.i18n.babel_wrapper import BabelWrapper
from common.i18n.locale_info import LocaleInfo
from common.logger import get_logger
from utils.file import file_fingerprint

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
        generate_doc: bool,
    ):
        self.locale_infos: dict[str, LocaleInfo] = locale_infos
        self.default_locale: str = default_locale
        new_i18n_strings: bool = False
        if self.i18n_source_files_changed():
            logger.info('Extracting i18n strings...')
            new_i18n_strings = self.extract_i18n_strings()
        mo_file_updated: bool = False
        for locale, locale_info in self.locale_infos.items():
            logger.info('Inspecting locale [%s]...', locale)
            po_file: Path = self.locale_po_file(locale)
            po_file_update_marker: Path = po_file.with_suffix('.updated')
            new_po_strings: bool = False
            if not po_file.is_file():
                new_po_strings = self.update_po_file(locale)
                po_file_update_marker.touch()
                logger.info('PO file [%s] has been created.', str(po_file.name))
            elif new_i18n_strings:
                new_po_strings = self.update_po_file(locale)
                po_file_update_marker.touch()
                if new_po_strings:
                    logger.info('PO file [%s] has been changed.', str(po_file.name))
            new_errors: bool = locale_info.control()
            locale_info.print_summary()
            mo_file: Path = self.locale_mo_file(locale)
            build_mo: bool = False
            if new_errors:
                logger.info('Errors found in PO file [%s].', str(po_file.name))
                build_mo = True
            elif new_po_strings:
                build_mo = True
            elif not mo_file.is_file():
                logger.info('MO file [%s] not found, creating it.', str(mo_file.name))
                build_mo = True
            elif po_file.lstat().st_mtime > mo_file.lstat().st_mtime:
                logger.info(
                    'MO file [%s] older than PO file [%s], rebuilding it.',
                    str(mo_file.name),
                    str(po_file.name),
                )
                build_mo = True
            elif (
                po_file_update_marker.exists()
                and po_file.lstat().st_mtime > po_file_update_marker.lstat().st_mtime
            ):
                logger.info(
                    'PO file [%s] has changed since last time updated.',
                    str(po_file.name),
                )
                build_mo = True
            else:
                logger.info(
                    'PO file [%s] is unchanged, no need to rebuild MO file [%s].',
                    str(po_file.name),
                    str(mo_file.name),
                )
            if build_mo:
                self.update_mo_file(locale)
                logger.info('Translations have been updated for locale [%s].', locale)
                mo_file_updated = True
        if generate_doc and mo_file_updated:
            self.write_markdown()
        self.ok: bool = True
        logger.info('Checking the translations...')
        for locale_info in self.locale_infos.values():
            if locale_info.error_messages:
                logger.error('Translations are not valid for some locales.')
                self.ok = False
                break
        for locale_info in self.locale_infos.values():
            if locale_info.empty_mandatory_messages:
                logger.error('Mandatory translations are missing for some locales.')
                self.ok = False
                break
        for locale_info in self.locale_infos.values():
            if not locale_info.default and locale_info.empty_optional_messages:
                logger.warning('Translations are missing for some locales.')
                self.ok = False
                break
        for locale_info in self.locale_infos.values():
            if locale_info.flagged_messages:
                logger.warning('Translations are flagged for some locales.')
                self.ok = False
                break
        if self.ok:
            logger.info('Translations OK.')

    @classmethod
    def i18n_source_files_changed(
        cls,
    ):
        """Returns True if at least one i18n source file has changed, False otherwise."""
        logger.info('Checking if i18n source files have been updated...')
        pattern_found: bool = False
        updated_file_found: bool = False
        fingerprints_file = TMP_DIR / 'i18n-src.json'
        old_fingerprints: dict[str, str] = {}
        try:
            with open(fingerprints_file) as f:
                old_fingerprints = json.load(f)
        except FileNotFoundError:
            updated_file_found = True
        new_fingerprints: dict[str, str] = {}
        with open(cls.config_file, 'r') as f:
            # looking for patterns in the Babel configuration file
            for line in f:
                if matches := re.match(r'\[\w+: *(.*)]', line):
                    pattern_found = True
                    for file in BASE_DIR.glob(matches.group(1)):
                        new_fingerprints[str(file)] = file_fingerprint(file).hex()
                        if not updated_file_found:
                            if str(file) not in old_fingerprints:
                                logger.info('File [%s] is new.', file)
                                updated_file_found = True
                            elif (
                                new_fingerprints[str(file)]
                                != old_fingerprints[str(file)]
                            ):
                                logger.info('File [%s] has been updated.', file.name)
                                updated_file_found = True
        if not pattern_found:
            logger.error('No file pattern found in [%s].', cls.config_file)
            return False
        if not updated_file_found:
            if cls.pot_file.is_file():
                logger.info('No source files updated, no need to rebuild the POT file.')
                return False
            logger.info('POT file not found, needs to be rebuilt.')
        with open(fingerprints_file, 'w') as f:
            json.dump(new_fingerprints, f)
        return True

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


class BabelMOFilesUpdater(BabelWrapper):
    """Update all the MO files.
    Usage:
    BabelMOFilesUpdater()
    """

    def __init__(
        self,
        locales: list[str],
    ):
        for locale in locales:
            po_file: Path = self.locale_po_file(locale)
            mo_file: Path = self.locale_mo_file(locale)
            build_mo: bool = False
            if not mo_file.is_file():
                logger.info('MO file [%s] not found, creating it.', str(mo_file.name))
                build_mo = True
            elif po_file.lstat().st_mtime > mo_file.lstat().st_mtime:
                logger.info(
                    'MO file [%s] older than PO file [%s], rebuilding it.',
                    str(mo_file.name),
                    str(po_file.name),
                )
                build_mo = True
            else:
                logger.debug(
                    'PO file [%s] is unchanged, no need to rebuild MO file [%s].',
                    str(po_file.name),
                    str(mo_file.name),
                )
            if build_mo:
                self.update_mo_file(locale)
                logger.info('Translations have been updated for locale [%s].', locale)
