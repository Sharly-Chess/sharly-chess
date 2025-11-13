import sys
from logging import Logger
from pathlib import Path

from babel.messages.frontend import CommandLineInterface

from common import BASE_DIR
from common.i18n.domains import Domain
from common.logger import get_logger, print_interactive_info

logger: Logger = get_logger()


class BabelDomainWrapper(Domain):
    """A class to wrap the Babel program, for a domain."""

    @staticmethod
    def run_babel_command(
        babel_command: str,
        babel_args: list,
        verbose: bool = False,
    ) -> int:
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
        # logger.debug('Running Babel %s...', f'[{" ".join(argv)}]')
        return CommandLineInterface().run(argv)
        # logger.debug('Babel returned %d.', return_code or 0)

    def extract_i18n_strings(self):
        """Updates the POT file from the source files."""
        # logger.debug('Babel configuration (%s):', self.config_file)
        # with open(self.config_file, 'r') as f:
        #    for line in f:
        #        if stripped_line := line.replace('\n', '').strip():
        #            logger.debug(stripped_line)
        self.run_babel_command(
            'extract',
            [
                f'--mapping-file={self.config_file}',
                f'--output-file={self.pot_file}',
                '--sort-output',
                '--add-location=never',
                '--no-wrap',
                '--omit-header',
                '--ignore-dirs="**/static"',
                f'{BASE_DIR}',
            ],
        )

    def update_po_file(
        self,
        locale: str,
    ):
        """Updates the PO file of the locale from the POT file."""
        po_file: Path = self.locale_po_file(locale)
        if not po_file.is_file():
            print_interactive_info(f'Initializing {po_file}...')
            po_file.parent.mkdir(parents=True, exist_ok=True)
            self.run_babel_command(
                'init',
                [
                    f'--locale={locale}',
                    f'--input-file={self.pot_file}',
                    f'--output-file={po_file}',
                ],
            )
        # logger.debug('Updating %s...', po_file)
        self.run_babel_command(
            'update',
            [
                f'--locale={locale}',
                f'--output-dir={self.locale_dir}',
                f'--input-file={self.pot_file}',
                f'--output-file={po_file}',
                '--no-fuzzy-matching',
                '--no-wrap',
                '--omit-header',
            ],
        )

    def update_mo_file(self, locale: str):
        """Compiles the PO file of the locale to the MO file."""
        # logger.debug('Compiling locale %s...', locale)
        self.run_babel_command(
            'compile',
            [
                '--use-fuzzy',
                '--domain=messages',
                f'--directory={self.locale_dir}',
                f'--locale={locale}',
            ],
        )
