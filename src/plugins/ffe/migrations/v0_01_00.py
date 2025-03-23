from dataclasses import dataclass
from sqlite3 import OperationalError
from typing import Literal, override

from plugins.utils import AbstractPluginMigration


@dataclass
class Column:
    name: str
    type_declaration: Literal['TEXT', 'INTEGER', 'FLOAT NOT NULL DEFAULT 0.0']
    _deprecated_name: str | None = None
    table: Literal['tournament'] = 'tournament'

    @property
    def deprecated_name(self) -> str:
        return f'deprecated_{self.name}'


class Migration(AbstractPluginMigration):
    def forward(self):
        # TODO replace by column creation once deprecated columns have been globally deleted
        self.database.execute(
            'ALTER TABLE `info` ADD `ffe_plugin_version` TEXT'
        )
        columns: list[Column] = [
            Column('ffe_id', 'INTEGER'),
            Column('ffe_password', 'TEXT'),
            Column(
                'ffe_last_upload',
                'FLOAT NOT NULL DEFAULT 0.0',
                'deprecated_last_ffe_upload',
            ),
            Column(
                'ffe_last_rules_upload',
                'FLOAT NOT NULL DEFAULT 0.0',
                'deprecated_last_ffe_rules_upload',
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

    def backward(self):
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `ffe_id`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `ffe_password`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `ffe_last_upload`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `ffe_last_rules_upload`'
        )
        self.database.execute(
            'ALTER TABLE `info` DROP COLUMN `ffe_plugin_version`'
        )
