import logging
import sys
from argparse import ArgumentParser

from utils.scripts import init_script

arguments = init_script()

from common.exception import SharlyChessException  # Noqa E402
from common.logger import (  # Noqa E402
    print_interactive_info,
    print_interactive_error,
    print_interactive_success,
    set_logging_config,
)
from data.loader import EventLoader  # Noqa E402
from database.sqlite.config.config_database import ConfigDatabase  # Noqa E402
from database.sqlite.event.event_database import EventDatabase  # Noqa E402
from database.sqlite.migration_database import MigrationDatabase  # Noqa E402


if __name__ == '__main__':
    parser = ArgumentParser(
        description='Command migrating one or more databases to a specific migration.'
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
    args = parser.parse_args(arguments)
    if not args.events and not args.all_events and not args.config:
        print_interactive_error(
            'No database selected, use one of the options '
            '"--events", "--all-events", "--config".'
        )
        sys.exit(1)
    if args.config and (args.events or args.all_events):
        print_interactive_error(
            "config and event databases can't be migrated at the same time."
        )
        sys.exit(1)
    if args.events and args.all_events:
        print_interactive_error(
            'Options "--events" and "--all-events" can\'t be used at the same time.'
        )
        sys.exit(1)
    if args.migration and args.validate:
        print_interactive_error(
            'Options "--migration" and "--validate" can\'t be used at the same time.'
        )
        sys.exit(1)
    databases: list[MigrationDatabase] = []
    if args.config:
        databases.append(ConfigDatabase(not args.validate))
    else:
        for event_id in args.events or EventLoader().all_event_ids():
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
            except SharlyChessException as e:
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

    set_logging_config(console_log_level=logging.DEBUG)
    for database in databases:
        with database:
            try:
                database.migration_managers[0].migrate(migration)
            except SharlyChessException as e:
                print_interactive_error(str(e))
