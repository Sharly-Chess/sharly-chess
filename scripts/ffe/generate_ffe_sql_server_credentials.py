from argparse import ArgumentParser, Namespace
from asyncio import run

from common.exception import PapiWebException
from common.logger import (
    print_interactive_error,
    print_interactive_info,
    print_interactive_success,
)
from plugins.ffe.ffe_sql_server import FFESqlServer


async def main():
    parser = ArgumentParser(
        description=('Generate credentials for the FFE online database.')
    )
    parser.add_argument(
        '--host',
        type=str,
        help=('The host.'),
        required=True,
    )
    parser.add_argument(
        '--user',
        type=str,
        help=('The user.'),
        required=True,
    )
    parser.add_argument(
        '--password',
        type=str,
        help='The password.',
        required=True,
    )
    parser.add_argument(
        '--database',
        type=str,
        help='The name of the database.',
        required=True,
    )
    args: Namespace = parser.parse_args()
    FFESqlServer.dump_credentials(
        args.host,
        args.user,
        args.password,
        args.database,
    )
    print_interactive_success(
        f'The credentials have been written to {FFESqlServer.CREDENTIALS_FILE}.'
    )
    print_interactive_info('Now testing the remote database...')
    try:
        async with FFESqlServer() as ffe_sql_server:
            async for player in await ffe_sql_server.search_player(
                'pascal aubry', limit=8
            ):
                print_interactive_info(f'{player=}')
    except PapiWebException as exception:
        print_interactive_error(f'{exception=}')
    print_interactive_info('Done.')


if __name__ == '__main__':
    run(main())
