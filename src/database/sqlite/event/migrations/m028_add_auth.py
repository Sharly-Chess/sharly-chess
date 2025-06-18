from data.auth.entities import Computer
from data.auth.roles import Role
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import LOCALHOST_ID, ANY_COMPUTER_ID, ANY_USER_ID
from database.sqlite.migration import BaseMigration


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
            (
                LOCALHOST_ID,
                False,
                False,
                True,
                Computer.LOCALHOST_IP,
                EventDatabase.dump_to_json_database_permissions(
                    {
                        Role.ADMINISTRATOR: None,
                    }
                ),
            ),
            (
                ANY_COMPUTER_ID,
                False,
                True,
                False,
                Computer.ANY_IP,
                EventDatabase.dump_to_json_database_permissions(
                    {
                        Role.SPECTATOR: None,
                    }
                ),
            ),
        ):
            self.database.execute(
                'INSERT INTO `computer`(`id`, `edit_properties`, `edit_permissions`, `active`, `ip`, `permissions`) VALUES (?, ?, ?, ?, ?, ?)',
                computer_data,
            )
        self.database.execute(
            'CREATE TABLE `user` ('
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
        for user_data in (
            (
                ANY_USER_ID,
                False,
                True,
                False,
                '',
                '',
                EventDatabase.dump_to_json_database_permissions(
                    {
                        Role.SPECTATOR: None,
                    }
                ),
            ),
        ):
            self.database.execute(
                'INSERT INTO `computer`(`id`, `edit_properties`, `edit_permissions`, `active`, `username`, `password`, `permissions`) VALUES (?, ?, ?, ?, ?, ?, ?)',
                user_data,
            )

    def backward(self):
        self.database.execute('DROP TABLE IF EXISTS `user`')
        self.database.execute('DROP TABLE IF EXISTS `computer`')
