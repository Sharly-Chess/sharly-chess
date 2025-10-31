#!/usr/bin/env python3
import sys
from argparse import ArgumentParser, Namespace
from asyncio import run
from pathlib import Path

from common.logger import print_interactive_success
from plugins.chess_results.utils import ChessResultsUtils

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


async def main():
    parser = ArgumentParser(
        description='Generate environment variables for Chess-Results.com.'
    )
    parser.add_argument(
        '--key',
        type=str,
        help='The AES key.',
        required=True,
    )
    parser.add_argument(
        '--iv',
        type=str,
        help='The AES IV.',
        required=True,
    )
    args: Namespace = parser.parse_args()
    ChessResultsUtils.dump_credentials(
        args.key,
        args.iv,
    )
    print_interactive_success(
        f'The credentials have been written to {ChessResultsUtils.CREDENTIALS_FILE}.'
    )


if __name__ == '__main__':
    run(main())
