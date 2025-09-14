from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'CREATE TABLE `account` ('
            '    `id` INTEGER NOT NULL,'
            '    `active` INTEGER NOT NULL DEFAULT 1,'
            '    `first_name` TEXT,'
            '    `last_name` TEXT,'
            '    `password_hash` TEXT,'
            '    `access_levels` TEXT,'
            '    `tournament_ids` TEXT,'
            '    PRIMARY KEY(`id` AUTOINCREMENT)'
            ')'
        )
        self.database.execute('ALTER TABLE `info` DROP COLUMN `update_password`')

    def backward(self):
        self.database.execute(
            'ALTER TABLE `info` ADD `update_password` TEXT',
        )
        self.database.execute('DROP TABLE IF EXISTS `account`')
