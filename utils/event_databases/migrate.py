import sys
from argparse import ArgumentParser

from packaging.version import Version

from common.logger import print_interactive_info, print_interactive_error, print_interactive_success
from data.loader import EventLoader
from database.sqlite.event_database import EventDatabase
from database.sqlite.event_migration import EventMigrationManager


if __name__ == '__main__':
    parser = ArgumentParser(
        description=(
            'Command migrating one or more '
            'event databases to a specific version.'
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
    parser.add_argument(
        '-a',
        '--all-events',
        action='store_true',
        help='Apply the migration to all the event databases.',
    )
    args = parser.parse_args()

    event_ids: list[str] = []
    if not args.event and not args.all_events:
        print_interactive_error(
            'No event selected, use one of the options '
            '"--event EVENT" or "--all-events"'
        )
        sys.exit(1)
    elif args.event and args.all_events:
        print_interactive_error(
            'Options "--event EVENT" and "--all-events" '
            'can\'t be used at the same time'
        )
        sys.exit(1)
    elif args.event:
        event_ids.append(args.event)
    elif args.all_events:
        event_ids = EventLoader().event_uniq_ids

    migration_manager = EventMigrationManager(True)
    version = (
        Version(args.version) if args.version else
        migration_manager.last_migration_version
    )
    for event_id in event_ids:
        with EventDatabase(event_id, True, False) as event_database:
            if event_database.version == version:
                print_interactive_info(
                    f'Database [{event_id}] already at version {version}'
                )
            elif migration_manager.migrate(event_database, version):
                print_interactive_success(
                    f'Database [{event_id}] migrated to version {version}'
                )
