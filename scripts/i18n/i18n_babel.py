import sys

from babel.messages.frontend import CommandLineInterface


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
