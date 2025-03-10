import sys
from argparse import ArgumentParser, Namespace

from packaging.version import Version

from common.logger import print_interactive_info, print_interactive_error, print_interactive_success
from data.loader import EventLoader
from database.sqlite.config.config_database import ConfigMigrationManager, ConfigDatabase
from database.sqlite.event.event_database import EventDatabase, EventMigrationManager
from database.sqlite.versioned_database import SQLiteVersionedDatabase

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
        action='append',
        help=(
            'Versions of the database to migrate to successively. '
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
    parser.add_argument(
        '-c',
        '--config',
        action='store_true',
        help='Migrate the configuration database (.scc).',
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Apply the migration to all the event databases and the configuration database.',
    )
    args: Namespace = parser.parse_args()

    if not args.event and not args.all_events and not args.config and not args.all:
        print_interactive_error(
            'No database selected, use one of the options '
            '"--event EVENT", "--all-events", "--config" or "--all".'
        )
        sys.exit(1)
    if args.all:
        if args.event or args.all_events or args.config:
            print_interactive_error(
                'Options "--event EVENT", "--all-events" and "--config" are '
                'ignored when option "--all" is used.'
            )
        del args.event
        args.all_events = True
        args.config = True
    if args.event and args.all_events:
        print_interactive_info(
            'Options "--event EVENT" and "--all-events" '
            'can\'t be used at the same time.'
        )
        sys.exit(1)
    event_ids: list[str] | None = None
    if args.event:
        event_ids = [args.event, ]
    elif args.all_events:
        event_ids = EventLoader().event_uniq_ids
    config: bool = False
    if args.config:
        config = True

    config_versions: list[Version] = []
    event_versions: list[Version] = []
    config_migration_manager: ConfigMigrationManager = ConfigMigrationManager(True)
    event_migration_manager: EventMigrationManager = EventMigrationManager(True)
    if args.version:
        print(args.version)
        for v in args.version:
            if v == 'current':
                if config:
                    config_versions.append(SQLiteVersionedDatabase.papi_web_version)
                if event_ids:
                    event_versions.append(SQLiteVersionedDatabase.papi_web_version)
            else:
                version = Version(v)
                max_version = max(version, SQLiteVersionedDatabase.papi_web_version)
                if config:
                    config_versions.append(
                        max(
                            min(
                                Version(v),
                                SQLiteVersionedDatabase.papi_web_version,
                                config_migration_manager.last_migration_version
                            ),
                            config_migration_manager.first_migration_version,
                        )
                    )
                if event_ids:
                    event_versions.append(
                        max(
                            min(
                                Version(v),
                                SQLiteVersionedDatabase.papi_web_version,
                                event_migration_manager.last_migration_version
                            ),
                            event_migration_manager.first_migration_version,
                        )
                    )
    else:
        if config:
            config_versions.append(
                max(
                    min(
                        SQLiteVersionedDatabase.papi_web_version,
                        config_migration_manager.last_migration_version
                    ),
                    config_migration_manager.first_migration_version,
                )
            )
        if event_ids:
            event_versions.append(
                max(
                    min(
                        SQLiteVersionedDatabase.papi_web_version,
                        event_migration_manager.last_migration_version
                    ),
                    event_migration_manager.first_migration_version,
                )
            )

    if config:
        for version in config_versions:
            with ConfigDatabase(True, False) as config_database:
                if config_database.version == version:
                    print_interactive_info(
                        f'Configuration database already at version {version}'
                    )
                elif event_migration_manager.migrate(config_database, version):
                    print_interactive_success(
                        f'Configuration database migrated to version {version}'
                    )
    for event_id in event_ids:
        for version in event_versions:
            with EventDatabase(event_id, True, False) as event_database:
                if event_database.version == version:
                    print_interactive_info(
                        f'Database [{event_id}] already at version {version}'
                    )
                elif event_migration_manager.migrate(event_database, version):
                    print_interactive_success(
                        f'Database [{event_id}] migrated to version {version}'
                    )
