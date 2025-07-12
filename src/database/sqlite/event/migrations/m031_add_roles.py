from database.sqlite.event.event_store import DEFAULT_CUSTOM_EXEC_MODE
from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'CREATE TABLE `device` ('
            '    `id` INTEGER NOT NULL,'
            '    `active` INTEGER NOT NULL DEFAULT 1,'
            '    `ip` TEXT,'
            '    `roles` TEXT,'
            '    `tournament_ids` TEXT,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    UNIQUE(`ip`)'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `account` ('
            '    `id` INTEGER NOT NULL,'
            '    `active` INTEGER NOT NULL DEFAULT 1,'
            '    `username` TEXT,'
            '    `password_hash` TEXT,'
            '    `roles` TEXT,'
            '    `tournament_ids` TEXT,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    UNIQUE(`username`)'
            ')'
        )
        self.database.execute(
            f'ALTER TABLE `info` ADD `custom_exec_mode` INTEGER NOT NULL DEFAULT {1 if DEFAULT_CUSTOM_EXEC_MODE else 0}',
        )
        self.database.execute('ALTER TABLE `info` DROP COLUMN `update_password`')

    def backward(self):
        self.database.execute(
            'ALTER TABLE `info` ADD `update_password` TEXT',
        )
        self.database.execute('ALTER TABLE `info` DROP COLUMN `custom_exec_mode`')
        self.database.execute('DROP TABLE IF EXISTS `account`')
        self.database.execute('DROP TABLE IF EXISTS `device`')
