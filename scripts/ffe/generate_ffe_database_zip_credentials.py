#!/usr/bin/env python3
import sys
from argparse import ArgumentParser, Namespace
from asyncio import run
from pathlib import Path

from plugins.ffe.ffe_database import FfeDatabase

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

from common.logger import print_interactive_success


async def main():
    parser = ArgumentParser(
        description='Generate credentials for the FFE local database.'
    )
    parser.add_argument(
        '--password',
        type=str,
        help='The password.',
        required=True,
    )
    args: Namespace = parser.parse_args()
    FfeDatabase.dump_credentials(
        args.password,
    )
    print_interactive_success(
        f'The credentials have been written to {FfeDatabase.CREDENTIALS_FILE}.'
    )


if __name__ == '__main__':
    run(main())
