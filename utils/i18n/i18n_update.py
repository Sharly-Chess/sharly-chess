import sys
from pathlib import Path

from babel.messages import Catalog, Message
from babel.messages.frontend import CommandLineInterface
from babel.messages.pofile import read_po

from common.i18n import default_locale, set_locale, _, locale_localized_name, locale_flag_url, trusted_locales, \
    translators
from common.logger import print_interactive_error, print_interactive_warning, print_interactive_info, \
    print_interactive_success, input_interactive, print_interactive_input
from utils.i18n.i18n_translate import I18nTranslator


def run_babel_command(
        babel_command: str,
        babel_args: list,
        quiet: bool = False,
):
    """ Run a Babel command using the command-line interface. """
    argv: list[str] = [sys.argv[0], ]
    if quiet:
        argv += ['-q', ]
    argv += [babel_command, ] + list(map(str, babel_args))  # map to ensure all args are passed as strings
    CommandLineInterface().run(argv)


class LocaleInfo:

    def __init__(
            self,
            id: str,
            locale_dir: Path,
            doc_dir: Path,
    ):
        self.id: str = id
        self.default: bool = id == default_locale
        self.locale_dir: Path = locale_dir
        self.po_file: Path = self.locale_dir / self.id / 'LC_MESSAGES' / 'messages.po'
        self.mo_file: Path = self.locale_dir / self.id / 'LC_MESSAGES' / 'messages.mo'
        self.doc_file: Path = doc_dir / f'i18n-{self.id}.md'
        self.messages: dict[str, Message] = {}
        self.empty_messages: dict[str, Message] = {}
        self.mandatory_messages: dict[str, Message] = {}
        self.empty_mandatory_messages: dict[str, Message] = {}
        self.flagged_messages: dict[str, dict[str, Message]] = {}

    def update(
            self,
            pot_file: Path,
    ) -> bool:
        """ Updates the PO file from the POT file, returns True if the locale is new. """
        new_locale: bool = False
        if not self.po_file.exists():
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
                '--no-wrap',
                '--omit-header',
            ],
            quiet=True,
        )
        return new_locale

    def compile(
            self,
    ):
        """ Compiles the PO file to the MO file. """
        print_interactive_info(f'- {self.mo_file}...')
        run_babel_command(
            'compile',
            [
                '--use-fuzzy',
                f'--directory={self.locale_dir}',
                f'--locale={self.id}',
            ],
            quiet=True,
        )

    @staticmethod
    def escape_gh_md(string: str) -> str:
        """ Escapes a string for GitHub markdown. """
        return string.replace('*', '\*')

    def control(self):
        # Read the catalog.
        print_interactive_info(f'- {self.mo_file}...')
        with open(self.po_file, 'rb') as f:
            catalog: Catalog = read_po(f)
        self.messages = {}
        self.empty_messages = {}
        self.empty_mandatory_messages = {}
        self.flagged_messages = {}
        # Control all the messages.
        for msg in catalog:
            if msg.id:
                self.messages[msg.id] = msg
                if isinstance(msg.id, str):
                    if not msg.string:
                        self.empty_messages[msg.id] = msg
                        continue
                else:
                    if not msg.string[0] or not msg.string[1]:
                        self.empty_messages[msg.id] = msg
                        continue
                if msg.id.__contains__('***'):
                    self.mandatory_messages[msg.id] = msg
                    if not msg.string:
                        self.empty_mandatory_messages[msg.id] = msg
                        continue
                for flag in msg.flags:
                    if flag != 'python-format':
                        if not flag in self.flagged_messages:
                            self.flagged_messages[flag] = {}
                        self.flagged_messages[flag][msg.id] = msg

    def write_markdown(self):
        """ Write a markdown file showing the status of this translation. """
        set_locale(self.id)
        with open(self.doc_file, 'w', encoding='utf-8') as f:
            f.write('<!--\n    WARNING: DO NOT EDIT!\n    This file has been generated by script i18n_update.\n-->\n\n')
            f.write('**[{text}](../README.md)**\n\n'.format(text=_('Return to documentation summary')))
            f.write('# Papi-web - {text}\n\n'.format(text=_("English translation *** TRANSLATE ! ***")))
            file: str = '/'.join(reversed([self.po_file.name, ] + [d.name for d in self.po_file.parents[:3]]))
            f.write('- [{text}](../{file})\n\n'.format(
                text=_('View file {file}').format(file=file),
                file=file))
            f.write('## {text}\n\n'.format(text=_('Summary'), locale=self.id))
            f.write(f'| locale=`{self.id}` | {locale_localized_name(self.id)} <img src="../src/web{locale_flag_url(self.id)}" style="height: 1em;"/> |\n')
            f.write('|--|:--:|\n')
            f.write('|{text}|{num}/{total}|\n'.format(
                text=_('Empty mandatory messages'),
                num=len(self.empty_mandatory_messages), total=len(self.mandatory_messages)))
            f.write('|{text}|{num}/{total}|\n'.format(
                text=_('Empty messages'), num=len(self.empty_messages), total=len(self.messages)))
            for flag, messages in self.flagged_messages.items():
                f.write('|{text}|{num}/{total}|\n'.format(
                    text=_('Message flagged [{flag}]'.format(flag=flag)),
                    num=len(self.flagged_messages[flag]), total=len(self.messages)))
            f.write('\n')
            f.write('## {text} ({num})\n\n'.format(
                text=_('Empty mandatory messages'), num=len(self.empty_mandatory_messages) or '-'))
            if self.empty_mandatory_messages:
                f.write('|{text1}|{text2}|\n'.format(text1=_('Message id'), text2=_('Locations')))
                f.write('|--|--|\n')
                for msg in self.empty_mandatory_messages.values():
                    if isinstance(msg.id, str):
                        text1: str = self.escape_gh_md(msg.id)
                    else:
                        text1: str = '**{s}** {st}<br/>**{p}** {pt}'.format(
                            s=_('Singular:'), st=self.escape_gh_md(msg.id[0]),
                            p=_('Plural:'), pt=self.escape_gh_md(msg.id[1]))
                    f.write('|{text1}|{text2}|\n'.format(
                        text1=text1,
                        text2='<br>'.join([f'{location[0]}:{location[1]}' for location in msg.locations])))
            f.write('## {text} ({num})\n\n'.format(
                text=_('Empty messages'), num=len(self.empty_messages) or '-'))
            if self.empty_messages:
                if self.default:
                    f.write(_('Empty messages are not shown for the default language.') + '\n\n')
                else:
                    f.write('|{text1}|{text2}|\n'.format(text1=_('Message id'), text2=_('Locations')))
                    f.write('|--|--|\n')
                    for msg in self.empty_messages.values():
                        if isinstance(msg.id, str):
                            text1: str = self.escape_gh_md(msg.id)
                        else:
                            text1: str = '**{s}** {st}<br/>**{p}** {pt}'.format(
                                s=_('Singular:'), st=self.escape_gh_md(msg.id[0]),
                                p=_('Plural:'), pt=self.escape_gh_md(msg.id[1]))
                        f.write('|{text1}|{text2}|\n'.format(
                            text1=text1,
                            text2='<br>'.join([f'{location[0]}:{location[1]}' for location in msg.locations])))
                    f.write('\n')
            f.write('## {text} ({num})\n\n'.format(
                text=_('Flagged messages'),
                num=sum([len(self.flagged_messages[flag]) for flag in self.flagged_messages])))
            for flag in self.flagged_messages:
                f.write('### {text} ({num})\n\n'.format(
                    text=_('Message flagged [{flag}]').format(flag=flag), num=len(self.flagged_messages[flag])))
                f.write('|{text1}|{text2}|{text3}|\n'.format(
                    text1=_('Message id'), text2=_('Translation'), text3=_('Locations')))
                f.write('|--|--|--|\n')
                for msg in self.flagged_messages[flag].values():
                    if isinstance(msg.id, str):
                        text1: str = self.escape_gh_md(msg.id)
                        text2: str = self.escape_gh_md(msg.string)
                    else:
                        text1: str = '**{s}** {st}<br/>**{p}** {pt}'.format(
                            s=_('Singular:'), st=self.escape_gh_md(msg.id[0]),
                            p=_('Plural:'), pt=self.escape_gh_md(msg.id[1]))
                        text2: str = '**{s}** {st}<br/>**{p}** {pt}'.format(
                            s=_('Singular:'), st=self.escape_gh_md(msg.string[0]),
                            p=_('Plural:'), pt=self.escape_gh_md(msg.string[1]))
                    f.write('|{text1}|{text2}|{text3}|\n'.format(
                        text1=text1, text2=text2,
                        text3='<br>'.join([f'{location[0]}:{location[1]}' for location in msg.locations])))
                f.write('\n')
        print_interactive_info(f'  -  {self.doc_file}.')

    def print_summary(self):
        """ print a summary of the locale. """
        print_interactive_info(
            f'- Locale [{self.id}]{" (default)" if self.default else ""}: {"OK" if not self.empty_messages and not self.flagged_messages else ""}')
        if self.empty_mandatory_messages:
            print_interactive_error(f'  * Empty mandatory messages ({len(self.empty_mandatory_messages)})')
            for msg_id in self.empty_mandatory_messages:
                print_interactive_error(f'    - [{msg_id}]')
        empty_messages_max: int = 5
        if self.empty_messages:
            if self.id == default_locale:
                print_interactive_info(f'  * Empty messages ({len(self.empty_messages)}), not listed for the default locale.')
            else:
                print_interactive_warning(f'  * Empty messages ({len(self.empty_messages)})')
                for msg_id in list(self.empty_messages.keys())[:empty_messages_max]:
                    print_interactive_warning(f'    - [{msg_id}]')
                if len(self.empty_messages) > empty_messages_max:
                    print_interactive_warning(f'    - ({len(self.empty_messages) - empty_messages_max} more)')
        if self.flagged_messages:
            flagged_messages_max: int = 5
            for flag, msgs in self.flagged_messages.items():
                print_interactive_warning(f'  * Messages flagged [{flag}] ({len(self.flagged_messages[flag])})')
                for msg_id in list(msgs.keys())[:flagged_messages_max]:
                    print_interactive_warning(f'    - [{msg_id}]')
                if len(self.flagged_messages[flag]) > flagged_messages_max:
                    print_interactive_warning(f'    - ({len(self.flagged_messages[flag]) - flagged_messages_max} more)')


class I18nUpdater:

    def __init__(
            self,
            locales: list[str],
    ):
        """ The path of the i18n files (this script should be run from the dev root). """
        self.locales: list[str] = locales
        self.locale_dir: Path = Path('locale')
        self.pot_file: Path = self.locale_dir / 'messages.pot'
        self.doc_dir: Path = Path('docs')
        self.doc_file: Path = self.doc_dir / '86-i18n.md'
        self.new_locales: list[str] = []
        print_interactive_info(f'Extracting i18n strings to {self.pot_file}...')
        self.extract()
        self.locale_infos: dict[str, LocaleInfo] = {
            locale: LocaleInfo(locale, self.locale_dir, self.doc_dir) for locale in locales
        }
        print_interactive_info('Updating PO files...')
        for locale_info in self.locale_infos.values():
            if locale_info.update(self.pot_file):
                self.new_locales.append(locale_info.id)
        print_interactive_info('Compiling PO files...')
        for locale_info in self.locale_infos.values():
            locale_info.compile()
        if self.new_locales:
            print_interactive_success('New locales created, please re-run.')
            return
        print_interactive_info('Inspecting PO files...')
        untrusted_locales_with_missing_translations: list[str] = []
        for locale_info in self.locale_infos.values():
            locale_info.control()
            if locale_info.id not in trusted_locales and locale_info.empty_messages:
                untrusted_locales_with_missing_translations.append(locale_info.id)
        self.print_summary()
        print_interactive_input(f'Some translations are missing for the following untrusted locales: {", ".join(untrusted_locales_with_missing_translations)}')
        if (input_interactive('Do you want to add the missing translations (y/N)? ').upper() or 'N') == 'Y':
            for locale in untrusted_locales_with_missing_translations:
                I18nTranslator(locale).add_missing_translations()
            print_interactive_info('Inspecting PO files...')
            for locale in untrusted_locales_with_missing_translations:
                self.locale_infos[locale].control()
            print_interactive_info('Compiling PO files...')
            for locale in untrusted_locales_with_missing_translations:
                self.locale_infos[locale].compile()
        print_interactive_info('Writing MD files...')
        self.write_markdown()
        self.print_summary()

    def extract(self, ):
        """ The configuration file used to extract stings from the source files. """
        extract_config_file: Path = Path() / 'utils' / 'i18n' / 'babel.cfg'
        run_babel_command(
            'extract',
            [
                f'--mapping-file={extract_config_file}',
                f'--output-file={self.pot_file}',
                '--no-wrap',
                '--omit-header',
                '.',
            ],
            quiet=True,
        )

    def write_markdown(self):
        """ Update the i18n doc file with the status of the translations. """
        for locale_info in self.locale_infos.values():
            locale_info.write_markdown()
        set_locale(default_locale)
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
                print_interactive_error(f'Could not edit [{self.doc_file}] (comment [{comment}] not found).')
                return
            comment: str = '<!-- DO NOT EDIT! (END) -->'
            comment_found: bool = False
            for line in f:
                if line.startswith(comment):
                    comment_found = True
                if comment_found:
                    lines_after_comment.append(line)
            if not comment_found:
                print_interactive_error(f'Could not edit [{self.doc_file}] (comment [{comment}] not found).')
                return
        lines: list[str] = []
        flags: set[str] = set()
        for locale in self.locale_infos:
            for flag in self.locale_infos[locale].flagged_messages:
                flags.add(flag)
        headers: list[str] = ['Locale', 'Messages', 'Empty messages', 'Empty mandatory messages', ]
        headers += [f'Messages flagged [{flag}]' for flag in flags]
        headers += ['Details', 'PO file', 'Translators', ]
        lines.append('| ' + ' | '.join(headers) +' |\n')
        lines.append('|--' + ('|:--:' * (len(headers)-1)) + '|\n')
        for locale, locale_info in self.locale_infos.items():
            line : str = f'|<img src="../src/web{locale_flag_url(locale)}" style="height: 1em;"/>&nbsp;``{locale}``&nbsp;{locale_localized_name(locale)} '
            line += f'| {len(locale_info.messages)} '
            line += f'| {len(locale_info.empty_messages)} '
            line += f'| {len(locale_info.empty_mandatory_messages)} '
            for flag in flags:
                line += f'| {len(locale_info.flagged_messages.get(flag, []))} '
            line += f'| [{locale_info.doc_file.name}]({locale_info.doc_file.name}) '
            line += f'| [{locale_info.po_file.name}](' \
                + '/'.join(reversed([locale_info.po_file.name, ] + [d.name for d in locale_info.po_file.parents[:3]] + ['..', ])) \
                + ') '
            translator_strings: list[str] = []
            for translator in translators[locale]:
                if translator['github_user']:
                    translator_strings.append(f'[{translator["name"]}](https://github.com/{translator["github_user"]})')
                else:
                    translator_strings.append(translator['name'])
            line += f'| {"<br/>".join(translator_strings)} |\n'
            lines.append(line)
        lines.append('\n')
        with open(self.doc_file, 'w', encoding='utf-8') as f:
            for line in lines_before_comment + lines + lines_after_comment:
                f.write(line)
        print_interactive_info(f'  -  {self.doc_file}.')

    def print_summary(self):
        """ Print a summary of all the locales. """
        for locale_info in self.locale_infos.values():
            locale_info.print_summary()

    def check_trusted_locales(self) -> bool:
        assert not self.new_locales
        print_interactive_info('Checking trusted locales...')
        perfect: bool = True
        for locale, locale_info in self.locale_infos.items():
            if locale in trusted_locales:
                if locale_info.empty_mandatory_messages:
                    print_interactive_error('Mandatory translations are missing for trusted locales.')
                    perfect = False
                    break
        for locale, locale_info in self.locale_infos.items():
            if locale in trusted_locales:
                if not locale_info.default and locale_info.empty_messages:
                    print_interactive_warning('Translations are missing for trusted locales.')
                    perfect = False
                    break
        for locale, locale_info in self.locale_infos.items():
            if locale in trusted_locales:
                if locale_info.flagged_messages:
                    print_interactive_warning('Translations are flagged for trusted locales.')
                    perfect = False
                    break
        if perfect:
            print_interactive_success('Translations seem perfect for trusted locales.')
        return perfect


if __name__ == '__main__':
    """ PO and MO files are automatically created from this list; to add a new locale, add it to the list. """
    updater = I18nUpdater([
        'en', 'fr',
        'de', 'el', 'es', 'it', 'nl', 'sv',
    ])
    if not updater.new_locales:
        updater.check_trusted_locales()
