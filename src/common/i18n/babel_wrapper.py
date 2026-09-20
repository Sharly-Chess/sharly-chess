from typing import cast
import os
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
        # Every argument is mapped to a string, so Babel receives no other type.
        argv += [babel_command, *(str(arg) for arg in babel_args)]
        # logger.debug('Running Babel %s...', f'[{" ".join(argv)}]')
        # Babel ships no annotations, so its entry point is untyped.
        return cast(int, CommandLineInterface().run(argv))  # type: ignore[no-untyped-call]
        # logger.debug('Babel returned %d.', return_code or 0)

    def extract_i18n_strings(self) -> None:
        """Updates the POT file from the source files."""
        self.run_babel_command(
            'extract',
            [
                f'--mapping-file={self.config_file}',
                f'--output-file={self.pot_file}',
                '--sort-output',
                '--add-location=never',
                '--add-comments=i18n:',
                '--no-wrap',
                '--omit-header',
                '--ignore-dirs="**/static"',
                f'{BASE_DIR}',
            ],
        )

    def update_po_file(
        self,
        locale: str,
    ) -> None:
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
                '--ignore-obsolete',
                '--no-wrap',
                '--omit-header',
            ],
        )

    def update_mo_file(self, locale: str) -> None:
        """Compiles the PO file of the locale to the MO file.

        The MO file is written next to the final one and moved into
        place: a reader never sees a half-written file, which is what a
        second process compiling the same locale at the same time (a
        pytest-xdist worker, the server under test) would otherwise get.
        """
        mo_file: Path = self.locale_mo_file(locale)
        partial_mo_file: Path = mo_file.with_name(f'{mo_file.stem}.{os.getpid()}.mo')
        self.run_babel_command(
            'compile',
            [
                '--use-fuzzy',
                f'--locale={locale}',
                f'--input-file={self.locale_po_file(locale)}',
                f'--output-file={partial_mo_file}',
            ],
        )
        partial_mo_file.replace(mo_file)
