from typing import override

from plugins.utils import AbstractPluginMigration


class Migration(AbstractPluginMigration):
    @override
    def forward(self):
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `ffe_last_upload`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `ffe_last_rules_upload`'
        )
        self.database.execute(
            f'ALTER TABLE `tournament` RENAME COLUMN '
            f'`deprecated_last_ffe_upload` TO `ffe_last_upload`'
        )
        self.database.execute(
            f'ALTER TABLE `tournament` RENAME COLUMN '
            f'`deprecated_last_ffe_rules_upload` TO `ffe_last_rules_upload`'
        )

    @override
    def backward(self):

        self.database.execute(
            f'ALTER TABLE `tournament` RENAME COLUMN '
            f'`ffe_last_upload` TO `deprecated_last_ffe_upload`'
        )
        self.database.execute(
            f'ALTER TABLE `tournament` RENAME COLUMN '
            f'`ffe_last_rules_upload` TO `deprecated_last_ffe_rules_upload`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD '
            '`ffe_last_rules_upload` FLOAT NOT NULL DEFAULT 0.0'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD '
            '`ffe_last_upload` FLOAT NOT NULL DEFAULT 0.0'
        )
