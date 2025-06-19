from database.sqlite.event.event_store import (
    anonymous_stored_account,
    localhost_stored_computer,
    unknown_stored_computer,
)
from database.sqlite.migration import BaseMigration
from database.sqlite.sqlite_database import SQLiteDatabase


class Migration(BaseMigration):
    def forward(self):
        self.backward()
        self.database.execute(
            'CREATE TABLE `computer` ('
            '    `id` INTEGER NOT NULL,'
            '    `edit_properties` INTEGER NOT NULL DEFAULT 1,'
            '    `edit_permissions` INTEGER NOT NULL DEFAULT 1,'
            '    `active` INTEGER NOT NULL DEFAULT 1,'
            '    `ip` TEXT,'
            '    `permissions` TEXT,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    UNIQUE(`ip`)'
            ')'
        )
        for computer_data in (
            localhost_stored_computer,
            unknown_stored_computer,
        ):
            self.database.execute(
                'INSERT INTO `computer`(`id`, `edit_properties`, `edit_permissions`, `active`, `ip`, `permissions`) VALUES (?, ?, ?, ?, ?, ?)',
                (
                    computer_data.id,
                    computer_data.edit_properties,
                    computer_data.edit_permissions,
                    computer_data.active,
                    computer_data.ip,
                    SQLiteDatabase.dump_to_json_database_field(
                        computer_data.permissions
                    ),
                ),
            )
        self.database.execute(
            'CREATE TABLE `account` ('
            '    `id` INTEGER NOT NULL,'
            '    `edit_properties` INTEGER NOT NULL DEFAULT 1,'
            '    `edit_permissions` INTEGER NOT NULL DEFAULT 1,'
            '    `active` INTEGER NOT NULL DEFAULT 1,'
            '    `username` TEXT,'
            '    `password` TEXT,'
            '    `permissions` TEXT,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    UNIQUE(`username`)'
            ')'
        )
        for account_data in (anonymous_stored_account,):
            self.database.execute(
                'INSERT INTO `account`(`id`, `edit_properties`, `edit_permissions`, `active`, `username`, `password`, `permissions`) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (
                    account_data.id,
                    account_data.edit_properties,
                    account_data.edit_permissions,
                    account_data.active,
                    account_data.username,
                    account_data.password,
                    SQLiteDatabase.dump_to_json_database_field(
                        account_data.permissions
                    ),
                ),
            )

    def backward(self):
        self.database.execute('DROP TABLE IF EXISTS `account`')
        self.database.execute('DROP TABLE IF EXISTS `computer`')
