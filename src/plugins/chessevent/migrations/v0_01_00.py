from dataclasses import dataclass
from sqlite3 import OperationalError
from typing import Literal, override

from plugins.utils import AbstractPluginMigration


@dataclass
class Column:
    table: Literal['info', 'tournament']
    name: str
    _deprecated_name: str | None = None
    type_declaration: Literal['TEXT'] = 'TEXT'

    @property
    def deprecated_name(self) -> str:
        return self._deprecated_name or f'deprecated_{self.name}'


class Migration(AbstractPluginMigration):
    @override
    def forward(self):
        # TODO replace by column creation once deprecated columns have been globally deleted
        self.database.execute(
            'ALTER TABLE `info` ADD `chessevent_plugin_version` TEXT'
        )
        columns: list[Column] = [
            Column('info', 'chessevent_user_id'),
            Column('info', 'chessevent_password'),
            Column('info', 'chessevent_event_id'),
            Column('tournament', 'chessevent_user_id'),
            Column('tournament', 'chessevent_password'),
            Column('tournament', 'chessevent_event_id'),
            Column('tournament', 'chessevent_tournament_name'),
            Column(
                'tournament',
                'chessevent_last_download_md5',
                'deprecated_last_chessevent_download_md5',
            ),
        ]
        for column in columns:
            try:
                self.database.execute(
                    f'ALTER TABLE `{column.table}` RENAME COLUMN '
                    f'`{column.deprecated_name}` TO `{column.name}`'
                )
            except OperationalError:
                self.database.execute(
                    f'ALTER TABLE `{column.table}` ADD '
                    f'`{column.name}` {column.type_declaration}'
                )

    @override
    def backward(self):
        self.database.execute(
            'ALTER TABLE `info` DROP COLUMN `chessevent_user_id`'
        )
        self.database.execute(
            'ALTER TABLE `info` DROP COLUMN `chessevent_password`'
        )
        self.database.execute(
            'ALTER TABLE `info` DROP COLUMN `chessevent_event_id`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `chessevent_user_id`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `chessevent_password`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `chessevent_event_id`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `chessevent_tournament_name`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN '
            '`chessevent_last_download_md5`'
        )
        self.database.execute(
            'ALTER TABLE `info` DROP COLUMN `chessevent_plugin_version`'
        )
