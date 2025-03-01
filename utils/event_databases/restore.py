import sys
from argparse import ArgumentParser

from packaging.version import Version

from common.papi_web_config import PapiWebConfig
from data.loader import EventBackup, EventBackupLoader


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

    args = parser.parse_args()
    loader = EventBackupLoader()
    event_id = args.event
    if args.version:
        version = Version(args.version)
        if version > PapiWebConfig.version:
            sys.stderr.write(
                f'Impossible to restore: Version selected ({version}) is newer'
                f' than the latest Papi Web version {PapiWebConfig.version}\n'
            )
            sys.exit(1)
    else:
        version = loader.latest_compatible_version(event_id)
        if not version:
            sys.stderr.write('No compatible backup to restore\n')
            sys.exit(1)

    to_restore: list[EventBackup] = []
    if event_id:
        backup = EventBackup(event_id, version)
        if not backup.exists:
            sys.stderr.write(
                'No backup to restore for event '
                f'{event_id} and version {version.public}\n'
            )
            sys.exit(1)
        to_restore.append(backup)
    else:
        to_restore = loader.version_backups(version)
        if not to_restore:
            sys.stderr.write(
                f'No backup to restore for version {version.public}\n'
            )
            sys.exit(1)

    for backup in to_restore:
        backup.restore()
        sys.stdout.write(
            f'Database "{backup.name}" restored to '
            f'version {backup.version.public}\n'
        )
