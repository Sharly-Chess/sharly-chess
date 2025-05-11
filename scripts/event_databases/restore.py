import sys
from argparse import ArgumentParser

from packaging.version import Version

from utils.scripts import init_script

arguments = init_script()

from common import SHARLY_CHESS_VERSION  # Noqa: E402
from common.logger import print_interactive_error, print_interactive_info  # Noqa: E402
from data.loader import EventBackup, EventBackupLoader  # Noqa: E402


if __name__ == '__main__':
    parser = ArgumentParser(
        description=(
            'Command restoring the event database backups. '
            'If there already exists an event database with the same id '
            'as a restored event, the existing database is overwritten.'
        )
    )
    parser.add_argument(
        '-v',
        '--version',
        type=str,
        help=(
            'Version of the database to restore. '
            'Defaults to the latest compatible version.'
        ),
    )
    parser.add_argument(
        '-e',
        '--event',
        type=str,
        help=(
            'ID of the event to restore. '
            'Defaults to all the events of the selected version.'
        ),
    )

    args = parser.parse_args(arguments)
    loader = EventBackupLoader()
    event_id = args.event
    if args.version:
        version = Version(args.version)
        if version > SHARLY_CHESS_VERSION:
            print_interactive_error(
                f'Impossible to restore: Version selected ({version}) is newer'
                f' than the latest Sharly Chess version {SHARLY_CHESS_VERSION}'
            )
            sys.exit(1)
    else:
        version = loader.latest_compatible_version(event_id)
        if not version:
            print_interactive_error('No compatible backup to restore')
            sys.exit(1)

    to_restore: list[EventBackup] = []
    if event_id:
        backup = EventBackup(event_id, version)
        if not backup.exists:
            print_interactive_error(
                'No backup to restore for event '
                f'{event_id} and version {version.public}'
            )
            sys.exit(1)
        to_restore.append(backup)
    else:
        to_restore = loader.version_backups(version)
        if not to_restore:
            print_interactive_error(
                f'No backup to restore for version {version.public}'
            )
            sys.exit(1)

    for backup in to_restore:
        backup.restore()
        print_interactive_info(
            f'Database "{backup.name}" restored to version {backup.version.public}'
        )
