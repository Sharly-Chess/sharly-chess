from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'CREATE TABLE `device` ('
            '    `id` INTEGER NOT NULL,'
            '    `edit_properties` INTEGER NOT NULL DEFAULT 1,'
            '    `edit_permissions` INTEGER NOT NULL DEFAULT 1,'
            '    `active` INTEGER NOT NULL DEFAULT 1,'
            '    `ip` TEXT,'
            '    `roles` TEXT,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    UNIQUE(`ip`)'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `account` ('
            '    `id` INTEGER NOT NULL,'
            '    `edit_properties` INTEGER NOT NULL DEFAULT 1,'
            '    `edit_permissions` INTEGER NOT NULL DEFAULT 1,'
            '    `active` INTEGER NOT NULL DEFAULT 1,'
            '    `username` TEXT,'
            '    `password_hash` TEXT,'
            '    `roles` TEXT,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    UNIQUE(`username`)'
            ')'
        )
        self.database.execute(
            'ALTER TABLE `info` ADD `exec_mode` INTEGER',
        )
        self.database.execute('ALTER TABLE `info` DROP COLUMN `update_password`')

    def backward(self):
        self.database.execute(
            'ALTER TABLE `info` ADD `update_password` TEXT',
        )
        self.database.execute('ALTER TABLE `info` DROP COLUMN `exec_mode`')
        self.database.execute('DROP TABLE IF EXISTS `account`')
        self.database.execute('DROP TABLE IF EXISTS `device`')
