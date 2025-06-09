from data.auth.entities import Computer
from data.auth.roles import Role
from database.sqlite.event.event_store import LOCALHOST_ID, ANY_COMPUTER_ID
from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.backward()
        self.database.execute(
            'CREATE TABLE `computer` ('
            '    `id` INTEGER NOT NULL,'
            '    `id` INTEGER NOT NULL DEFAULT 0,'
            '    `ip` TEXT,'
            '    PRIMARY KEY(`id` AUTOINCREMENT)'
            ')'
        )
        for computer_data in (
            (
                LOCALHOST_ID,
                Computer.LOCALHOST_IP,
            ),
            (
                ANY_COMPUTER_ID,
                Computer.ANY_IP,
            ),
        ):
            self.database.execute(
                'INSERT INTO `computer`(`id`, `ip`, `locked`) VALUES (?, ?, ?)',
                computer_data + (True,),
            )
        self.database.execute(
            'CREATE TABLE `computer_permission` ('
            '    `id` INTEGER NOT NULL,'
            '    `locked` INTEGER NOT NULL DEFAULT 0,'
            '    `active` INTEGER NOT NULL DEFAULT 1,'
            '    `computer_id` INTEGER NOT NULL,'
            '    `role_id` INTEGER NOT NULL,'
            '    `tournament_uniq_ids` TEXT,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    FOREIGN KEY (`computer_id`) REFERENCES `computer`(`id`) ON DELETE CASCADE'
            ')'
        )
        for computer_permission_data in (
            (
                LOCALHOST_ID,
                Role.ADMINISTRATOR.value,
                True,
            ),
            (
                ANY_COMPUTER_ID,
                Role.SPECTATOR.value,
                False,
            ),
        ):
            self.database.execute(
                'INSERT INTO `computer`(`computer_id`, `role_id`, `locked`) VALUES (?, ?, ?)',
                computer_permission_data,
            )
        self.database.execute(
            'CREATE TABLE `user` ('
            '    `id` INTEGER NOT NULL,'
            '    `username` TEXT,'
            '    `password` TEXT,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    UNIQUE(`username`)'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `user_permission` ('
            '    `id` INTEGER NOT NULL,'
            '    `active` INTEGER NOT NULL,'
            '    `user_id` INTEGER NOT NULL,'
            '    `role_id` INTEGER NOT NULL,'
            '    `tournament_uniq_ids` TEXT,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE'
            ')'
        )

    def backward(self):
        self.database.execute('DROP TABLE IF EXISTS `user_permission`')
        self.database.execute('DROP TABLE IF EXISTS `user`')
        self.database.execute('DROP TABLE IF EXISTS `computer_permission`')
        self.database.execute('DROP TABLE IF EXISTS `computer`')
