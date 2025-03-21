from argparse import ArgumentParser, Namespace

from common.exception import PapiWebException
from common.logger import print_interactive_error, print_interactive_info
from plugins.ffe.ffe_sql_server import FFESqlServer


def main():
    parser = ArgumentParser(
        description=(
            'Generate credentials for the FFE online database.'
        )
    )
    parser.add_argument(
        '--host',
        type=str,
        help=(
            'The host.'
        ),
        required=True,
    )
    parser.add_argument(
        '--user',
        type=str,
        help=(
            'The user.'
        ),
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
    try:
        with FFESqlServer() as ffe_sql_server:
            for player in ffe_sql_server.search_player('pascal aubry', limit=8):
                print_interactive_info(f'{player=}')
    except PapiWebException as exception:
        print_interactive_error(f'{exception=}')

if __name__ == '__main__':
    main()
