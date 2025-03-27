from plugins.utils import AbstractPluginMigration


class Migration(AbstractPluginMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `ffe_last_upload`')
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `ffe_last_rules_upload`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` RENAME COLUMN '
            '`deprecated_last_ffe_upload` TO `ffe_last_upload`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` RENAME COLUMN '
            '`deprecated_last_ffe_rules_upload` TO `ffe_last_rules_upload`'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `tournament` RENAME COLUMN '
            '`ffe_last_upload` TO `deprecated_last_ffe_upload`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` RENAME COLUMN '
            '`ffe_last_rules_upload` TO `deprecated_last_ffe_rules_upload`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD '
            '`ffe_last_rules_upload` FLOAT NOT NULL DEFAULT 0.0'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `ffe_last_upload` FLOAT NOT NULL DEFAULT 0.0'
        )
