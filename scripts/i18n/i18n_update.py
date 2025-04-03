import os
import re
import sys
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from babel.messages import Catalog, Message
from babel.messages.frontend import CommandLineInterface
from babel.messages.pofile import read_po, write_po

# force PAPI_WEB_EXPERIMENTAL to True to compile untrusted locales
os.environ['PAPI_WEB_EXPERIMENTAL'] = '1'

sys.path.extend(
    map(
        str,
        [
            Path(__file__).parents[2],  # The root path
            Path(__file__).parents[2]
            / 'src',  # The path to the sources of the application
        ],
    )
)

from common.i18n import (
    DEFAULT_LOCALE,
    locale_localized_name,
    locale_flag_url,
    trusted_locales,
    translators,
)
from common.logger import (
    print_interactive_error,
    print_interactive_warning,
    print_interactive_info,
    print_interactive_success,
    input_interactive,
    print_interactive_input,
)


def run_babel_command(
    babel_command: str,
    babel_args: list,
    quiet: bool = False,
):
    """Run a Babel command using the command-line interface."""
    argv: list[str] = [
        sys.argv[0],
    ]
    if quiet:
        argv += [
            '-q',
        ]
    argv += [
        babel_command,
    ] + list(map(str, babel_args))  # map to ensure all args are passed as strings
    CommandLineInterface().run(argv)


class LocaleInfo:
    def __init__(
        self,
        id_: str,
        locale_dir: Path,
        trusted: bool,
    ):
        self.id: str = id_
        self.default: bool = id_ == DEFAULT_LOCALE
        self.locale_dir: Path = locale_dir
        self.po_file: Path = self.locale_dir / self.id / 'LC_MESSAGES' / 'messages.po'
        self.mo_file: Path = self.locale_dir / self.id / 'LC_MESSAGES' / 'messages.mo'
        self.trusted: bool = trusted
        self.messages: dict[str, Message] = {}
        self.error_messages: dict[str, Message] = {}
        self.empty_optional_messages: dict[str, Message] = {}
        self.mandatory_messages: dict[str, Message] = {}
        self.empty_mandatory_messages: dict[str, Message] = {}
        self.flagged_messages: dict[str, dict[str, Message]] = {}

    def update_and_compile(
        self,
        pot_file: Path,
    ) -> bool:
        """Updates the PO file from the POT file,
        compiles the PO file to the MO file,
        returns True if the locale is new."""
        new_locale: bool = False
        if not self.po_file.is_file():
            print_interactive_info(f'- {self.po_file.parent}...')
            self.po_file.parent.mkdir(parents=True, exist_ok=True)
            run_babel_command(
                'init',
                [
                    f'--locale={self.id}',
                    f'--input-file={pot_file}',
                    f'--output-file={self.po_file}',
                ],
                quiet=True,
            )
            new_locale = True
        print_interactive_info(f'- {self.po_file}...')
        run_babel_command(
            'update',
            [
                f'--locale={self.id}',
                f'--output-dir={self.locale_dir}',
                f'--input-file={pot_file}',
                f'--output-file={self.po_file}',
                '--no-fuzzy-matching',
                '--no-wrap',
                '--omit-header',
            ],
            quiet=True,
        )
        if not self.mo_file.is_file():
            new_locale = True
        self.compile()
        return new_locale

    def compile(
        self,
    ):
        """Compiles the PO file to the MO file."""
        print_interactive_info(f'- {self.mo_file}...')
        run_babel_command(
            'compile',
            [
                '--use-fuzzy',
            ]
            + [
                f'--directory={self.locale_dir}',
                f'--locale={self.id}',
            ],
            quiet=False,
        )

    @staticmethod
    def escape_gh_md(string: str) -> str:
        """Escapes a string for GitHub markdown."""
        return string.replace('*', r'\*')

    @staticmethod
    def message_is_empty(msg: Message):
        if isinstance(msg.id, str):
            return not msg.string
        else:
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
        if isinstance(msg.id, str):
            if self.sorted_tokens(msg.id) != self.sorted_tokens(msg.string):
                msg.user_comments.append(
                    f'Error: tokens differ between [{msg.id}] and [{msg.string}]'
                )
                msg.string = ''
                error = True
        else:
            for i in reversed(range(len(msg.id))):
                if self.sorted_tokens(msg.id[i]) != self.sorted_tokens(msg.string[i]):
                    msg.user_comments.append(
                        f'Error: tokens differ between [{msg.id[i]}] and [{msg.string[i]}]'
                    )
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
            if len(msg.string) > 5 * len(msg.id):
                msg.user_comments.append(
                    f'Error: translation [{msg.string}] is much too long compared to initial [{msg.id}]'
                )
                msg.string = ''
                error = True
        else:
            for i in reversed(range(len(msg.id))):
                if len(msg.string[i]) > 5 * len(msg.id[i]):
                    msg.user_comments.append(
                        f'Error: translation [{msg.string}] is much too long compared to initial [{msg.id}]'
                    )
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
            if msg.id:
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


class I18nUpdater:
    def __init__(
        self,
        trusted_locales: list[str],
        untrusted_locales: list[str],
    ):
        """The path of the i18n files (this script should be run from the dev root)."""
        self.trusted_locales: list[str] = trusted_locales
        self.untrusted_locales: list[str] = untrusted_locales
        self.locale_dir: Path = Path('locale')
        self.pot_file: Path = self.locale_dir / 'messages.pot'
        self.doc_dir: Path = Path('docs')
        self.doc_file: Path = self.doc_dir / '86-i18n.md'
        self.new_locales: list[str] = []
        print_interactive_info(f'Extracting i18n strings to {self.pot_file}...')
        self.extract()
        self.locale_infos: dict[str, LocaleInfo] = OrderedDict()
        for locale in self.trusted_locales:
            self.locale_infos[locale] = LocaleInfo(
                locale, self.locale_dir, trusted=True
            )
        for locale in self.untrusted_locales:
            self.locale_infos[locale] = LocaleInfo(
                locale, self.locale_dir, trusted=False
            )
        print_interactive_info('Updating PO files...')
        for locale_info in self.locale_infos.values():
            if locale_info.update_and_compile(self.pot_file):
                self.new_locales.append(locale_info.id)
        if self.new_locales:
            print_interactive_success('New locales created, please re-run.')
            return
        print_interactive_info('Inspecting PO files...')
        untrusted_locales_with_missing_translations: list[str] = []
        for locale_info in self.locale_infos.values():
            locale_info.control()
            if (
                locale_info.id not in self.trusted_locales
                and locale_info.empty_optional_messages
            ):
                untrusted_locales_with_missing_translations.append(locale_info.id)
        print_interactive_info('Compiling PO files...')
        for locale_info in self.locale_infos.values():
            if not locale_info.error_messages:
                locale_info.compile()
        self.print_summary()
        print_interactive_info('Writing MD files...')
        self.write_markdown()
        if untrusted_locales_with_missing_translations:
            print_interactive_input(
                f'Some translations are missing for the following untrusted locales: {", ".join(untrusted_locales_with_missing_translations)}'
            )
            if (
                input_interactive(
                    'Do you want to add the missing translations (y/N)? '
                ).upper()
                or 'N'
            ) == 'Y':
                # import here not to create a dependency from export.py to translate stuff
                try:
                    from scripts.i18n.i18n_translate import I18nTranslator
                except ModuleNotFoundError as error:
                    print_interactive_error(
                        f'Could not import I18nTranslator: {error}.'
                    )
                    print_interactive_error(
                        "Make sure all the needed modules for translation are installed by running 'pip install -e .[translate]'."
                    )
                    sys.exit(1)
                for locale in untrusted_locales_with_missing_translations:
                    I18nTranslator(locale).add_missing_translations()
                print_interactive_info('Inspecting PO files...')
                for locale in untrusted_locales_with_missing_translations:
                    self.locale_infos[locale].control()
                print_interactive_info('Compiling PO files...')
                for locale in untrusted_locales_with_missing_translations:
                    if not self.locale_infos[locale].error_messages:
                        self.locale_infos[locale].compile()
                self.print_summary()
                print_interactive_info('Writing MD files...')
                self.write_markdown()

    def extract(
        self,
    ):
        """The configuration file used to extract stings from the source files."""
        extract_config_file: Path = Path() / 'scripts' / 'i18n' / 'babel.cfg'
        run_babel_command(
            'extract',
            [
                f'--mapping-file={extract_config_file}',
                f'--output-file={self.pot_file}',
                '--sort-output',
                '--add-location=never',
                '--no-wrap',
                '--omit-header',
                '.',
            ],
            quiet=True,
        )

    def write_markdown(self):
        """Update the i18n doc file with the status of the translations."""
        lines_before_comment: list[str] = []
        lines_after_comment: list[str] = []
        # Read the lines until the expected comment is found
        with open(self.doc_file, 'rt', encoding='utf-8') as f:
            comment: str = '<!-- DO NOT EDIT! (START) -->'
            comment_found: bool = False
            for line in f:
                lines_before_comment.append(line)
                if line.startswith(comment):
                    comment_found = True
                    break
            if not comment_found:
                print_interactive_error(
                    f'Could not edit [{self.doc_file}] (comment [{comment}] not found).'
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
                    f'Could not edit [{self.doc_file}] (comment [{comment}] not found).'
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
        with open(self.doc_file, 'w', encoding='utf-8') as f:
            for line in lines_before_comment + lines + lines_after_comment:
                f.write(line)
        print_interactive_info(f'  -  {self.doc_file}.')

    def print_summary(self):
        """Print a summary of all the locales."""
        for locale_info in self.locale_infos.values():
            locale_info.print_summary()

    def check_trusted_locales(self) -> bool:
        assert not self.new_locales
        print_interactive_info('Checking trusted locales...')
        perfect: bool = True
        for locale, locale_info in self.locale_infos.items():
            if locale in trusted_locales:
                if locale_info.empty_mandatory_messages:
                    print_interactive_error(
                        'Mandatory translations are missing for trusted locales.'
                    )
                    perfect = False
                    break
        for locale, locale_info in self.locale_infos.items():
            if locale in trusted_locales:
                if not locale_info.default and locale_info.empty_optional_messages:
                    print_interactive_warning(
                        'Translations are missing for trusted locales.'
                    )
                    perfect = False
                    break
        for locale, locale_info in self.locale_infos.items():
            if locale in trusted_locales:
                if locale_info.flagged_messages:
                    print_interactive_warning(
                        'Translations are flagged for trusted locales.'
                    )
                    perfect = False
                    break
        if perfect:
            print_interactive_success('Translations seem perfect for trusted locales.')
        return perfect


if __name__ == '__main__':
    untrusted_locales: list[str] = []
    if (
        input_interactive('Do you want to update the untrusted locales (y/N)? ').upper()
        or 'N'
    ) == 'Y':
        untrusted_locales = [
            'de',
            'el',
            'es',
            'it',
            'nl',
            'sv',
        ]
    # PO and MO files are automatically created from this list; to add a new locale, add it to the list.
    updater = I18nUpdater(
        trusted_locales=[
            'en',
            'fr',
        ],
        untrusted_locales=untrusted_locales,
    )
    if not updater.new_locales:
        updater.check_trusted_locales()
