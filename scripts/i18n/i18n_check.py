import re
import time
from datetime import datetime
from pathlib import Path

from babel.messages import Catalog, Message
from babel.messages.pofile import read_po, write_po

from common import BASE_DIR
from common.i18n.babel import BabelWrapper
from common.i18n import (
    DEFAULT_LOCALE,
    locale_localized_name,
    locale_flag_url,
    translators,
    locales,
)
from common.logger import (
    print_interactive_error,
    print_interactive_warning,
    print_interactive_info,
    print_interactive_success,
)


class LocaleInfo:
    def __init__(
        self,
        id_: str,
        locale_dir: Path,
    ):
        self.id: str = id_
        self.default: bool = id_ == DEFAULT_LOCALE
        self.locale_dir: Path = locale_dir
        self.po_file: Path = self.locale_dir / self.id / 'LC_MESSAGES' / 'messages.po'
        self.mo_file: Path = self.locale_dir / self.id / 'LC_MESSAGES' / 'messages.mo'
        self.messages: dict[str, Message] = {}
        self.error_messages: dict[str, Message] = {}
        self.empty_optional_messages: dict[str, Message] = {}
        self.mandatory_messages: dict[str, Message] = {}
        self.empty_mandatory_messages: dict[str, Message] = {}
        self.flagged_messages: dict[str, dict[str, Message]] = {}

    @staticmethod
    def escape_gh_md(string: str) -> str:
        """Escapes a string for GitHub markdown."""
        return string.replace('*', r'\*')

    @staticmethod
    def message_is_empty(msg: Message):
        if isinstance(msg.id, str):
            assert isinstance(msg.string, str)
            return not msg.string
        else:
            assert isinstance(msg.string, tuple)
            return not msg.string[0] or not msg.string[1]

    @staticmethod
    def sorted_tokens(string: str) -> list[str]:
        """Returns the sorted tokens of a string."""
        tokens: list[str] = []
        # ignore everything after *** (mandatory strings with instructions for the translators)
        if matches := re.match(r'^(.*)\s+\*\*\*\s+.*$', string):
            string = matches.group(1)
        # now really extract the tokens
        while True:
            token: str | None = None
            if match := re.search(r'{[^}]*}', string):  # Looking for {name}
                token = match.group()
            elif match := re.search(
                r'%%[sflt]', string
            ):  # Looking for %%s, %%f, %%l and %%t
                token = match.group()
            elif match := re.search(
                r'%[sflt]', string
            ):  # Looking for %s, %f, %l and %t
                token = match.group()
            elif match := re.search(
                r'%\([^)]*\)[ds]', string
            ):  # Looking for %(name)s or %(name)d
                token = match.group()
            if token:
                # string = string.replace(token, f'{self.token_replacement}_{len(tokens)}', 1)
                string = string.replace(token, '', 1)
                tokens.append(token)
            else:
                break
        return sorted(tokens)

    def compare_message_tokens(self, msg: Message) -> bool:
        error: bool = False
        if isinstance(msg.string, str):
            assert isinstance(msg.id, str)
            if self.sorted_tokens(msg.id) != self.sorted_tokens(msg.string):
                msg.user_comments = [
                    f'Error: tokens differ between [{msg.id}] and [{msg.string}]',
                ]
                msg.string = ''
                error = True
        else:
            assert isinstance(msg.id, tuple)
            assert isinstance(msg.string, tuple)
            for i in reversed(range(len(msg.id))):
                if self.sorted_tokens(msg.id[i]) != self.sorted_tokens(msg.string[i]):
                    msg.user_comments = [
                        f'Error: tokens differ between [{msg.id[i]}] and [{msg.string[i]}]',
                    ]
                    msg.string = tuple(
                        [
                            '',
                        ]
                        * len(msg.id)
                    )
                    error = True
                    break
        return not error

    @staticmethod
    def check_message_length(msg: Message) -> bool:
        error: bool = False
        if isinstance(msg.id, str):
            assert isinstance(msg.string, str)
            if len(msg.string) > 5 * len(msg.id):
                msg.user_comments = [
                    f'Error: translation [{msg.string}] is much too long compared to initial [{msg.id}]',
                ]
                msg.string = ''
                error = True
        else:
            assert isinstance(msg.id, tuple)
            assert isinstance(msg.string, tuple)
            for i in reversed(range(len(msg.id))):
                if len(msg.string[i]) > 5 * len(msg.id[i]):
                    msg.user_comments = [
                        f'Error: translation [{msg.string}] is much too long compared to initial [{msg.id}]',
                    ]
                    msg.string = tuple(
                        [
                            '',
                        ]
                        * len(msg.id)
                    )
                    error = True
                    break
        return not error

    def control(self):
        # Read the catalog.
        print_interactive_info(f'- Reading {self.po_file}...')
        with open(self.po_file, 'rb') as f:
            catalog: Catalog = read_po(f)
        self.messages = {}
        self.error_messages = {}
        self.empty_optional_messages = {}
        self.empty_mandatory_messages = {}
        self.flagged_messages = {}
        # Control all the messages.
        for msg in catalog:
            if isinstance(msg.id, str) and msg.id:
                self.messages[msg.id] = msg
                if msg.id.__contains__('***'):
                    self.mandatory_messages[msg.id] = msg
                    if self.message_is_empty(msg):
                        self.empty_mandatory_messages[msg.id] = msg
                        continue
                else:
                    if self.message_is_empty(msg):
                        self.empty_optional_messages[msg.id] = msg
                        continue
                if not self.compare_message_tokens(msg):
                    self.error_messages[msg.id] = msg
                    continue
                if not self.check_message_length(msg):
                    self.error_messages[msg.id] = msg
                    continue
                for flag in msg.flags:
                    if flag not in [
                        'python-format',
                        'error',
                    ]:
                        if flag not in self.flagged_messages:
                            self.flagged_messages[flag] = {}
                        self.flagged_messages[flag][msg.id] = msg
        print_interactive_info(f'- Writing {self.po_file}...')
        with open(self.po_file, 'wb') as f:
            write_po(f, catalog, width=0, omit_header=True)

    def print_summary(self):
        """print a summary of the locale."""
        print_interactive_info(
            f'- Locale [{self.id}]{" (default)" if self.default else ""}: {"OK" if not self.empty_optional_messages and not self.flagged_messages else ""}'
        )
        if self.error_messages:
            print_interactive_error(f'  * Error messages ({len(self.error_messages)})')
            for msg_id in self.error_messages:
                print_interactive_error(f'    - [{msg_id}]')
        if self.empty_mandatory_messages:
            print_interactive_error(
                f'  * Empty mandatory messages ({len(self.empty_mandatory_messages)})'
            )
            for msg_id in self.empty_mandatory_messages:
                print_interactive_error(f'    - [{msg_id}]')
        empty_messages_max: int = 3
        if self.empty_optional_messages:
            if self.id == DEFAULT_LOCALE:
                print_interactive_info(
                    f'  * Empty optional messages ({len(self.empty_optional_messages)}), not listed for the default locale.'
                )
            else:
                print_interactive_warning(
                    f'  * Empty messages ({len(self.empty_optional_messages)})'
                )
                for msg_id in list(self.empty_optional_messages.keys())[
                    :empty_messages_max
                ]:
                    print_interactive_warning(f'    - [{msg_id}]')
                if len(self.empty_optional_messages) > empty_messages_max:
                    print_interactive_warning(
                        f'    - ({len(self.empty_optional_messages) - empty_messages_max} more)'
                    )
        if self.flagged_messages:
            flagged_messages_max: int = 3
            for flag in sorted(self.flagged_messages.keys()):
                print_interactive_warning(
                    f'  * Messages flagged [{flag}] ({len(self.flagged_messages[flag])})'
                )
                for msg_id in list(self.flagged_messages[flag].keys())[
                    :flagged_messages_max
                ]:
                    print_interactive_warning(f'    - [{msg_id}]')
                if len(self.flagged_messages[flag]) > flagged_messages_max:
                    print_interactive_warning(
                        f'    - ({len(self.flagged_messages[flag]) - flagged_messages_max} more)'
                    )


class I18nChecker:
    def __init__(self):
        # The path of the i18n files (this script should be run from the dev root).
        self.locale_dir: Path = BASE_DIR / 'locale'
        self.pot_file: Path = self.locale_dir / 'messages.pot'
        self.ok: bool = True
        print_interactive_info(f'Extracting i18n strings to {self.pot_file}...')
        self.locale_infos: dict[str, LocaleInfo] = {
            locale: LocaleInfo(locale, self.locale_dir) for locale in locales
        }
        BabelWrapper.extract_i18n_strings(verbose=False)
        for locale, locale_info in self.locale_infos.items():
            BabelWrapper.update_po_file(locale, verbose=True)
            locale_info.control()
            locale_info.print_summary()
            BabelWrapper.update_mo_file(locale, verbose=True)
        self.print_summary()
        print_interactive_info('Writing MD files...')
        self.write_markdown()
        print_interactive_info('Checking translations...')
        self.check()

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
                print_interactive_error(
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
                print_interactive_error(
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
            line: str = f'|<img src="../src/web{locale_flag_url(locale)}" style="height: 1em;"/>&nbsp;``{locale}``&nbsp;{locale_localized_name(locale)} '
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
            for translator in translators[locale]:
                if translator['github_user']:
                    translator_strings.append(
                        f'[{translator["name"]}](https://github.com/{translator["github_user"]})'
                    )
                else:
                    translator_strings.append(translator['name'])
            line += f'| {"<br/>".join(translator_strings)} |\n'
            lines.append(line)
        lines.append(
            f'Last update: {datetime.strftime(datetime.fromtimestamp(time.time()), "%Y-%m-%d %H:%M")}\n'
        )
        with open(doc_file, 'w', encoding='utf-8') as f:
            for line in lines_before_comment + lines + lines_after_comment:
                f.write(line)
        print_interactive_info(f'  -  {doc_file}.')

    def print_summary(self):
        """Print a summary of all the locales."""
        for locale_info in self.locale_infos.values():
            locale_info.print_summary()

    def check(self):
        print_interactive_info('Checking locales...')
        for locale, locale_info in self.locale_infos.items():
            if locale in locales:
                if locale_info.empty_mandatory_messages:
                    print_interactive_error(
                        'Mandatory translations are missing for some locales.'
                    )
                    self.ok = False
                    break
        for locale, locale_info in self.locale_infos.items():
            if locale in locales:
                if not locale_info.default and locale_info.empty_optional_messages:
                    print_interactive_warning(
                        'Translations are missing for some locales.'
                    )
                    self.ok = False
                    break
        for locale, locale_info in self.locale_infos.items():
            if locale in locales:
                if locale_info.flagged_messages:
                    print_interactive_warning(
                        'Translations are flagged for some locales.'
                    )
                    self.ok = False
                    break
        if self.ok:
            print_interactive_success('Translations seem perfect.')


if __name__ == '__main__':
    I18nChecker()
