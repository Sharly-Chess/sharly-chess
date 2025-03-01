import sys
from argparse import ArgumentParser

from packaging.version import Version

from data.loader import EventLoader
from database.sqlite.event_database import EventDatabase
from database.sqlite.event_migration import EventMigrationManager


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
            'Version of the database to migrate to. '
            'Defaults to the last version.'
        ),
    )
    parser.add_argument(
        '-e',
        '--event',
        type=str,
        help='ID of the event to migrate. Defaults to all the events.',
    )

    args = parser.parse_args()
    migration_manager = EventMigrationManager()
    version = (
        Version(args.version) if args.version else
        migration_manager.last_migration_version
    )
    event_ids = [args.event] if args.event else EventLoader().event_uniq_ids
    for event_id in event_ids:
        with EventDatabase(event_id, True, False) as event_database:
            if event_database.version == version:
                sys.stdout.write(
                    f'Database [{event_id}] already at version {version}\n'
                )
            else:
                migration_manager.migrate(event_database, version)
                sys.stdout.write(
                    f'Database [{event_id}] migrated to version {version}\n'
                )
