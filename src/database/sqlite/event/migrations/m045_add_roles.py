from database.sqlite.migration import BaseMigration
from database.sqlite.sqlite_database import SQLiteDatabase


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
        for account_id, access_levels in {
            1: [
                'ADMINISTRATION',
            ],
            2: [
                'CHECK_IN',
                'RESULTS_ENTRY',
            ],
        }.items():
            self.database.execute(
                'INSERT INTO `account`(`id`, `access_levels`) VALUES (?, ?)',
                (account_id, SQLiteDatabase.dump_to_json_database_field(access_levels)),
            )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `info` ADD `update_password` TEXT',
        )
        self.database.execute('DROP TABLE IF EXISTS `account`')
