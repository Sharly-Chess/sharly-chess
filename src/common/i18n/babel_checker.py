import time
from datetime import datetime
from logging import Logger
from pathlib import Path

from common import BASE_DIR
from common.i18n.utils import locale_flag_url, locale_localized_name
from common.i18n.babel_wrapper import BabelWrapper
from common.i18n.locale_info import LocaleInfo
from common.logger import get_logger

logger: Logger = get_logger()


class BabelChecker(BabelWrapper):
    def __init__(
        self,
        locale_infos: dict[str, LocaleInfo],
        default_locale: str,
    ):
        self.locale_infos: dict[str, LocaleInfo] = locale_infos
        self.default_locale: str = default_locale
        new_i18n_strings: bool = False
        if self.i18n_files_changed():
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

    def write_markdown(self):
        """Update the i18n doc file with the status of the translations."""
        doc_file: Path = BASE_DIR / 'docs' / 'technical-appendices' / 'i18n.md'
        lines_before_comment: list[str] = []
        lines_after_comment: list[str] = []
        # Read the lines until the expected comment is found
        with open(doc_file, 'rt', encoding='utf-8') as f:
            comment: str = '<!-- DO NOT EDIT! (START) -->'
            comment_found: bool = False
            for line in f:
                lines_before_comment.append(line)
                if line.startswith(comment):
                    comment_found = True
                    break
            if not comment_found:
                logger.error(
                    f'Could not edit [{doc_file}] (comment [{comment}] not found).'
                )
                return
            comment: str = '<!-- DO NOT EDIT! (END) -->'
            comment_found: bool = False
            for line in f:
                if line.startswith(comment):
                    comment_found = True
                if comment_found:
                    lines_after_comment.append(line)
            if not comment_found:
                logger.error(
                    f'Could not edit [{doc_file}] (comment [{comment}] not found).'
                )
                return
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
        for locale, locale_info in self.locale_infos.items():
            line: str = f'|<img src="../../src/web{locale_flag_url(locale)}" style="height: 1em;"/>&nbsp;``{locale}``&nbsp;{locale_localized_name(locale)} '
            line += f'| {len(locale_info.messages)} '
            line += f'| {len(locale_info.empty_optional_messages)} '
            line += f'| {len(locale_info.empty_mandatory_messages)} '
            for flag in flags:
                line += f'| {len(locale_info.flagged_messages.get(flag, []))} '
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
        with open(doc_file, 'w', encoding='utf-8') as f:
            for line in lines_before_comment + lines + lines_after_comment:
                f.write(line)
        logger.info('Wrote [%s].', doc_file)
