import sys
from argparse import ArgumentParser, Namespace
from typing import Iterator

from packaging.version import Version

from common import PAPI_WEB_VERSION
from common.logger import (
    print_interactive_info,
    print_interactive_error,
    print_interactive_success,
    print_interactive_warning,
)
from data.loader import EventLoader
from database.sqlite.config.config_database import (
    ConfigMigrationManager,
    ConfigDatabase,
)
from database.sqlite.event.event_database import EventDatabase, EventMigrationManager
from database.sqlite.migration import AbstractMigrationManager

if __name__ == '__main__':

    def parse_args() -> (list[str], bool, list[str]):
        parser = ArgumentParser(
            description=(
                'Command migrating one or more event databases to a specific version.'
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
            args.event = None
            args.all_events = True
            args.config = True
        if args.event and args.all_events:
            print_interactive_info(
                'Options "--event EVENT" and "--all-events" '
                "can't be used at the same time."
            )
            sys.exit(1)
        args_event_ids: list[str] | None = None
        if args.event:
            args_event_ids = [
                args.event,
            ]
        elif args.all_events:
            args_event_ids = EventLoader().event_uniq_ids
        return (
            args_event_ids,
            args.config,
            args.version
            or [
                'current',
            ],
        )

    def database_correct_version(
        migration_manager: AbstractMigrationManager,
        version_string: str,
        warning: str,
    ) -> Version:
        version: Version
        if version_string == 'current':
            version: Version = PAPI_WEB_VERSION
        else:
            version = Version(version_string)
        correct_version: Version = max(
            min(version, PAPI_WEB_VERSION, migration_manager.last_migration_version),
            migration_manager.first_migration_version,
        )
        if version != correct_version:
            print_interactive_warning(
                warning.format(
                    version=version,
                    correct_version=correct_version,
                )
            )
        return correct_version

    def config_database_correct_version(
        migration_manager: ConfigMigrationManager,
        version_string: str,
    ) -> Version:
        return database_correct_version(
            migration_manager,
            version_string,
            'Version {version} is not valid for a '
            'configuration database, rectified to {correct_version}.',
        )

    def event_database_correct_version(
        migration_manager: EventMigrationManager,
        version_string: str,
    ) -> Version:
        return database_correct_version(
            migration_manager,
            version_string,
            'Version {version} is not valid for an '
            'event database, rectified to {correct_version}.',
        )

    event_ids, config, version_strings = parse_args()
    if config:
        config_migration_manager: ConfigMigrationManager = ConfigMigrationManager(True)
        config_versions: Iterator[Version] = (
            config_database_correct_version(config_migration_manager, version_string)
            for version_string in version_strings
        )
        for config_version in config_versions:
            with ConfigDatabase(True, False) as config_database:
                if config_database.version == config_version:
                    print_interactive_info(
                        f'Configuration database already at version {config_version}'
                    )
                elif config_migration_manager.migrate(config_database, config_version):
                    print_interactive_success(
                        f'Configuration database migrated to version {config_version}'
                    )
    if event_ids:
        event_migration_manager: EventMigrationManager = EventMigrationManager(True)
        event_versions = [
            event_database_correct_version(event_migration_manager, version_string)
            for version_string in version_strings
        ]
        for event_id in event_ids:
            for event_version in event_versions:
                with EventDatabase(event_id, True, False) as event_database:
                    if event_database.version == event_version:
                        print_interactive_info(
                            f'Database [{event_id}] already at version {event_version}'
                        )
                    elif event_migration_manager.migrate(event_database, event_version):
                        print_interactive_success(
                            f'Database [{event_id}] migrated to version {event_version}'
                        )
