import logging
import sys
from argparse import ArgumentParser, Namespace

# Needs to be imported first to avoid circular import
from plugins.manager import plugin_manager # Noqa

from common.exception import PapiWebException
from common.logger import (
    configure_logger,
    print_interactive_info,
    print_interactive_error,
    print_interactive_success,
)
from data.loader import EventLoader
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.migration_database import MigrationDatabase


if __name__ == '__main__':
    parser = ArgumentParser(
        description=(
            'Command migrating one or more '
            'databases to a specific migration.'
        )
    )
    parser.add_argument(
        '-e',
        '--events',
        type=str,
        nargs='+',
        help='ID of the events to migrate.',
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
        '-m',
        '--migration',
        type=str,
        help=(
            'Select the migration to migrate to. '
            'Can be the index of the migration or the full name. '
            '"zero" or 0 to rollback before the first migration. '
            'Defaults to the latest migration.'
        ),
    )
    parser.add_argument(
        '-v',
        '--validate',
        action='store_true',
        help='Validate the databases.',
    )
    args: Namespace = parser.parse_args()
    if not args.events and not args.all_events and not args.config:
        print_interactive_error(
            'No database selected, use one of the options '
            '"--events", "--all-events", "--config".'
        )
        sys.exit(1)
    if args.config and (args.events or args.all_events):
        print_interactive_error(
            'config and event databases can\'t be migrated at the same time.'
        )
        sys.exit(1)
    if args.events and args.all_events:
        print_interactive_error(
            'Options "--events" and "--all-events" '
            'can\'t be used at the same time.'
        )
        sys.exit(1)
    if args.migration and args.validate:
        print_interactive_error(
            'Options "--migration" and "--validate" '
            'can\'t be used at the same time.'
        )
        sys.exit(1)
    databases: list[MigrationDatabase] = []
    if args.config:
        databases.append(ConfigDatabase(not args.validate))
    else:
        for event_id in args.events or EventLoader().event_uniq_ids:
            databases.append(EventDatabase(event_id, not args.validate))

    if args.validate:
        for database in databases:
            print_interactive_info(
                f'Validating database [{database.file.name}]...', end=''
            )
            try:
                with database:
                    if database.check_status():
                        print_interactive_success('OK')
                    else:
                        print_interactive_info('TO UPDATE')
            except PapiWebException as e:
                print_interactive_error(f'NOK\n\t{e}')
        sys.exit(0)

    migration: str | None = None
    if args.migration:
        migration_manager = databases[0].migration_managers[0]
        if args.migration in ['0', 'zero']:
            migration = migration_manager.MIGRATION_ZERO
        elif str(args.migration).isdigit():
            migration = migration_manager.migration_by_index.get(
                int(args.migration), None
            )
            if migration is None:
                print_interactive_error(
                    f'no migration found with index [{args.migration}]'
                )
                sys.exit(1)
        else:
            migration = args.migration

    configure_logger(logging.DEBUG)
    for database in databases:
        with database:
            try:
                database.migration_managers[0].migrate(migration)
            except PapiWebException as e:
                print_interactive_error(str(e))
