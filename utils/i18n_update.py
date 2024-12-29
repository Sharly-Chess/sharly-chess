import sys
from logging import Logger
from pathlib import Path

from babel.messages import Catalog, Message
from babel.messages.frontend import CommandLineInterface
from babel.messages.pofile import read_po

from common import get_logger
from common.i18n import default_locale
from common.papi_web_config import PapiWebConfig

logger: Logger = get_logger()

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

def extract_strings_to_template(
    extract_config_file: Path,
    pot_file: Path,
):
    print(f'Extracting i18n strings to {pot_file}...')
    run_babel_command(
        'extract',
        [
            f'--mapping-file={extract_config_file}',
            f'--output-file={pot_file}',
            '--no-wrap',
            '--omit-header',
            '.',
        ],
        quiet=True,
    )

def update_po_file(
        locale_dir: Path,
        pot_file: Path,
        locale: str,
        po_file: Path):
    if not po_file.exists():
        print(f'- {po_file.parent}...')
        po_file.parent.mkdir(parents=True, exist_ok=True)
        run_babel_command(
            'init',
            [
                f'--locale={locale}',
                f'--input-file={pot_file}',
                f'--output-file={po_file}',
            ],
            quiet=True,
        )
    print(f'- {po_file}...')
    run_babel_command(
        'update',
        [
            f'--locale={locale}',
            f'--output-dir={locale_dir}',
            f'--input-file={pot_file}',
            f'--output-file={po_file}',
            '--no-wrap',
            '--omit-header',
        ],
        quiet=True,
    )

def update_po_files(
        locale_dir: Path,
        pot_file: Path,
        po_files: dict[str, Path]):
    print(f'Updating PO files...')
    for locale, po_file in po_files.items():
        update_po_file(locale_dir, pot_file, locale, po_file)


def compile_po_files(
        locale_dir: Path
):
    print(f'Compiling PO files...')
    run_babel_command(
        'compile',
        [
            '--use-fuzzy',
            f'--directory={locale_dir}',
        ],
        quiet=True,
    )

def inspect_po_files(
    po_files: dict[str, Path],
):
    print(f'Inspecting PO files...')
    for locale, po_file in po_files.items():
        with open(po_file, 'rb') as f:
            catalog: Catalog = read_po(f)
        flagged_messages: dict[str, list[Message]] = {}
        empty_messages: list[Message] = []
        for msg in catalog:
            if msg.id:
                if not msg.string:
                    if locale != default_locale:
                        empty_messages.append(msg)
                else:
                    for flag in msg.flags:
                        if flag != 'python-format':
                            if not flag in flagged_messages:
                                flagged_messages[flag] = []
                            flagged_messages[flag].append(msg)
        print(f'- Locale [{locale}]{" (default)" if locale == default_locale else ""}: {"OK" if not empty_messages and not flagged_messages else ""}')
        if locale != default_locale:
            if empty_messages:
                print(f'  * Empty messages ({len(empty_messages)})')
                for msg in empty_messages:
                    print(f'    - [{msg.id}]')
        if flagged_messages:
            for flag, msgs in flagged_messages.items():
                print(f'  * Messages flagged [{flag}] ({len(flagged_messages)})')
                for msg in msgs:
                    print(f'    - [{msg.id}]')

def main(
        extract_config_file: Path,
        locale_dir: Path,
        locales: list[str],
):
    """ The template file for all locales. """
    pot_file: Path = locale_dir / 'messages.pot'
    extract_strings_to_template(extract_config_file, pot_file)
    po_files: dict[str, Path] = {
        locale: locale_dir / locale / 'LC_MESSAGES' / 'messages.po' for locale in locales
    }
    update_po_files(locale_dir, pot_file, po_files)
    compile_po_files(locale_dir)
    inspect_po_files(po_files)
    print('Done.')

""" PO and MO files are automatically created from this list; oo add a new locale, add it to this list. """
LOCALES: list[str] = ['en', 'fr', ]

""" The configuration file used to extract stings from the source files. """
EXTRACT_CONFIG_FILE: Path = PapiWebConfig.base_dir / 'utils' / 'babel.cfg'

""" The path of the i18n files (this script should be run from the dev root. """
LOCALE_DIR: Path = PapiWebConfig.base_dir / 'locale'

if __name__ == '__main__':
    main(EXTRACT_CONFIG_FILE, LOCALE_DIR, LOCALES)
