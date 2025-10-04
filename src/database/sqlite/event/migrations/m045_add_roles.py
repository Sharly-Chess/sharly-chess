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
            '    PRIMARY KEY(`id` AUTOINCREMENT)'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `account_permission` ('
            '   `account_id` INTEGER NOT NULL,'
            '   `access_level` TEXT NOT NULL,'
            '   `tournament_id` INTEGER,'
            '   FOREIGN KEY (`account_id`) REFERENCES `account`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`tournament_id`) REFERENCES `tournament`(`id`) ON DELETE CASCADE,'
            '   UNIQUE(`account_id`, `access_level`, `tournament_id`)'
            ')'
        )
        self.database.execute('ALTER TABLE `info` DROP COLUMN `update_password`')

    def backward(self):
        self.database.execute(
            'ALTER TABLE `info` ADD `update_password` TEXT',
        )
        self.database.execute('DROP TABLE IF EXISTS `account_permission`')
        self.database.execute('DROP TABLE IF EXISTS `account`')
