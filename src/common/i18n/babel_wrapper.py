import shutil
import sys
from logging import Logger
from pathlib import Path

from babel.messages.frontend import CommandLineInterface

from common import BASE_DIR
from common.logger import get_logger
from utils.file import file_fingerprint

logger: Logger = get_logger()


class BabelWrapper:
    locale_dir: Path = BASE_DIR / 'locale'
    pot_file: Path = locale_dir / 'messages.pot'
    config_file: Path = BASE_DIR / 'src' / 'common' / 'i18n' / 'babel.cfg'

    @staticmethod
    def run_babel_command(
        babel_command: str,
        babel_args: list,
        verbose: bool = False,
    ):
        """Run a Babel command using the command-line interface."""
        argv: list[str] = [
            sys.argv[0],
        ]
        if not verbose:
            argv += [
                '-q',
            ]
        argv += [
            babel_command,
        ] + list(map(str, babel_args))  # map to ensure all args are passed as strings
        logger.debug('Running Babel %s...', f'[{" ".join(argv)}]')
        return_code: int = CommandLineInterface().run(argv)
        logger.debug('Babel returned %d.', return_code or 0)

    @classmethod
    def extract_i18n_strings(cls) -> bool:
        """Updates the POT file from the source files, returns True if the POT file has changed, False otherwise."""
        logger.debug('Babel configuration (%s):', cls.config_file)
        with open(cls.config_file, 'r') as f:
            for line in f:
                if stripped_line := line.replace('\n', '').strip():
                    logger.debug(stripped_line)
        pot_fingerprint: bytes
        if cls.pot_file.is_file():
            pot_fingerprint = file_fingerprint(cls.pot_file)
        else:
            pot_fingerprint = bytearray()
        tmp_file: Path = cls.pot_file.with_suffix('.tmp')
        cls.run_babel_command(
            'extract',
            [
                f'--mapping-file={cls.config_file}',
                f'--output-file={tmp_file}',
                '--sort-output',
                '--add-location=never',
                '--no-wrap',
                '--omit-header',
                '--ignore-dirs="src\\web\\static"',
                f'{BASE_DIR}',
            ],
        )
        if changed := (file_fingerprint(tmp_file) != pot_fingerprint):
            shutil.move(tmp_file, cls.pot_file)
        else:
            tmp_file.unlink()
        return changed

    @classmethod
    def locale_po_file(
        cls,
        locale: str,
    ) -> Path:
        return cls.locale_dir / locale / 'LC_MESSAGES' / 'messages.po'

    @classmethod
    def update_po_file(cls, locale: str):
        """Updates the PO file of the locale from the POT file, returns True if the PO file has changed."""
        po_file: Path = cls.locale_po_file(locale)
        po_fingerprint: bytes
        if not po_file.is_file():
            po_fingerprint = bytearray()
            logger.info('Initializing %s...', po_file)
            po_file.parent.mkdir(parents=True, exist_ok=True)
            cls.run_babel_command(
                'init',
                [
                    f'--locale={locale}',
                    f'--input-file={cls.pot_file}',
                    f'--output-file={po_file}',
                ],
            )
        else:
            po_fingerprint = file_fingerprint(po_file)
        logger.debug('Updating %s...', po_file)
        tmp_file: Path = po_file.with_suffix('.tmp')
        shutil.copy(po_file, tmp_file)
        cls.run_babel_command(
            'update',
            [
                f'--locale={locale}',
                f'--output-dir={cls.locale_dir}',
                f'--input-file={cls.pot_file}',
                f'--output-file={tmp_file}',
                '--no-fuzzy-matching',
                '--no-wrap',
                '--omit-header',
            ],
        )
        if changed := (file_fingerprint(tmp_file) != po_fingerprint):
            shutil.move(tmp_file, po_file)
        else:
            tmp_file.unlink()
        return changed

    @classmethod
    def update_mo_file(cls, locale: str):
        """Compiles the PO file of the locale to the MO file."""
        logger.debug('Compiling locale %s...', locale)
        cls.run_babel_command(
            'compile',
            [
                '--use-fuzzy',
                f'--directory={cls.locale_dir}',
                f'--locale={locale}',
            ],
        )

    @classmethod
    def locale_mo_file(
        cls,
        locale: str,
    ) -> Path:
        return cls.locale_po_file(locale).with_suffix('.mo')
