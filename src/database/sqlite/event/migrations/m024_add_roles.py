from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.backward()
        self.database.execute(
            'CREATE TABLE `client` ('
            '    `id` INTEGER NOT NULL,'
            '    `name` TEXT NOT NULL,'
            '    `username` TEXT,'
            '    `password` TEXT,'
            '    `ip` TEXT,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `permission` ('
            '    `id` INTEGER NOT NULL,'
            '    `client_id` INTEGER NOT NULL,'
            '    `role_id` INTEGER NOT NULL,'
            '    `tournament_id` INTEGER,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    FOREIGN KEY (`client_id`) REFERENCES `client`(`id`) ON DELETE CASCADE,'
            '    FOREIGN KEY (`tournament_id`) REFERENCES `tournament`(`id`) ON DELETE CASCADE'
            ')'
        )

    def backward(self):
        self.database.execute('DROP TABLE IF EXISTS `permission`')
        self.database.execute('DROP TABLE IF EXISTS `client`')
