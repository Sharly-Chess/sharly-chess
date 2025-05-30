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
    ):
        self.locale_infos: dict[str, LocaleInfo] = locale_infos
        self.default_locale: str = default_locale
        new_i18n_strings: bool = False
        if self.i18n_source_files_changed():
            logger.info('Extracting i18n strings...')
            new_i18n_strings = self.extract_i18n_strings()
            if new_i18n_strings:
                logger.info(
                    'I18n strings have changed, the PO/MO files need to be rebuilt.'
                )
            else:
                logger.info(
                    'I18n strings are unchanged, no need to rebuild the PO/MO files.'
                )
        mo_file_updated: bool = False
        for locale, locale_info in self.locale_infos.items():
            po_file: Path = self.locale_po_file(locale)
            mo_file: Path = self.locale_mo_file(locale)
            if new_i18n_strings or not po_file.is_file():
                new_po_strings = self.update_po_file(locale)
            else:
                new_po_strings = False
            new_errors: bool = locale_info.control()
            locale_info.print_summary()
            if new_errors or new_po_strings or not mo_file.is_file():
                self.update_mo_file(locale)
                logger.info('Translations have been updated for locale [%s].', locale)
                mo_file_updated = True
        if mo_file_updated:
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
                    for file in Path('.').glob(matches.group(1)):
                        new_fingerprints[str(file)] = file_fingerprint(file).hex()
                        if not updated_file_found:
                            if str(file) not in old_fingerprints:
                                logger.info(
                                    'File [%s] is new, the POT file need to be rebuild.',
                                    file,
                                )
                                updated_file_found = True
                            elif (
                                new_fingerprints[str(file)]
                                != old_fingerprints[str(file)]
                            ):
                                logger.info(
                                    'File [%s] has been updated, the POT file needs to be rebuilt.',
                                    file,
                                )
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
            self.update_mo_file(locale)
