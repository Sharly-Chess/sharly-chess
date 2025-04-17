from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('DROP TABLE IF EXISTS `client_controller`')
        self.database.execute(
            'CREATE TABLE `client_controller` ('
            '    `id` INTEGER NOT NULL,'
            '    `uniq_id` TEXT NOT NULL,'
            '    `name` TEXT,'
            '    `public` INTEGER,'
            '    `last_update` FLOAT,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    UNIQUE(`uniq_id`)'
            ')'
        )

    def backward(self):
        self.database.execute('DROP TABLE IF EXISTS `client_controller`')
