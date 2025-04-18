from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('DROP TABLE IF EXISTS `client_controller`')
        self.database.execute(
            'CREATE TABLE `client_controller` ('
            '    `id` INTEGER NOT NULL,'
            '    `uniq_id` TEXT NOT NULL,'
            '    `name` TEXT NOT NULL,'
            '    `public` INTEGER,'
            '    `screen_id` INTEGER,'
            '    `rotator_id` INTEGER,'
            '    `last_update` FLOAT,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    UNIQUE(`uniq_id`),'
            '    FOREIGN KEY (`screen_id`) REFERENCES `screen`(`id`) ON DELETE SET NULL,'
            '    FOREIGN KEY (`rotator_id`) REFERENCES `rotator`(`id`) ON DELETE SET NULL'
            ')'
        )

    def backward(self):
        self.database.execute('DROP TABLE IF EXISTS `client_controller`')
