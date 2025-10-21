import logging
import sys
from argparse import ArgumentParser

from plugins.manager import plugin_manager
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
        '--plugin',
        type=str,
        help=(
            'When migrating event databases, choose to migrate from the '
            'timeline of a plugin instead of the main timeline.'
        ),
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

    def incompatible_options_error(option1: str, option2: str):
        if getattr(args, option1.replace('-', '_')) and getattr(
            args, option2.replace('-', '_')
        ):
            print_interactive_error(
                f'Options [--{option1}] and [--{option2}] '
                "can't be used at the same time."
            )
            sys.exit(1)

    incompatible_options_error('config', 'plugin')
    incompatible_options_error('config', 'events')
    incompatible_options_error('config', 'all-events')
    incompatible_options_error('events', 'all-events')
    incompatible_options_error('validate', 'migration')
    incompatible_options_error('validate', 'plugin')

    databases: list[MigrationDatabase] = []
    if args.config:
        databases.append(ConfigDatabase(not args.validate))
    else:
        for event_id in args.events or EventLoader().all_event_ids():
            databases.append(
                EventDatabase(
                    event_id, not args.validate, check_dirty_tournaments=False
                )
            )

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

    def get_migration_manager(database_: MigrationDatabase):
        if not args.plugin:
            return database_.migration_managers[0]
        plugin = next(
            (
                plugin
                for plugin in plugin_manager.all_plugins
                if plugin.id == args.plugin
            ),
            None,
        )
        if not plugin:
            print_interactive_error(f'Plugin [{args.plugin}] not found.')
            sys.exit(1)
        if not plugin.base_migration_module:
            print_interactive_error(
                f'Plugin [{args.plugin}] does not support migrations.'
            )
            sys.exit(1)
        assert isinstance(database_, EventDatabase)
        return plugin.get_migration_manager(database_)

    migration: str | None = None
    if args.migration:
        migration_manager = get_migration_manager(databases[0])
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
        get_migration_manager(database).migrate(migration)
