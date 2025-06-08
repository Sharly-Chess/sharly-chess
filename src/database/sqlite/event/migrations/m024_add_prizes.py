from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'CREATE TABLE `prize_group` ('
            '   `id` INTEGER NOT NULL,'
            '   `tournament_id` INTEGER NOT NULL,'
            '   `name` TEXT NOT NULL,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   UNIQUE(`id`),'
            '   FOREIGN KEY (`tournament_id`) REFERENCES '
            '   `tournament`(`id`) ON DELETE CASCADE'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `prize_category` ('
            '   `id` INTEGER NOT NULL,'
            '   `prize_group_id` INTEGER NOT NULL,'
            '   `name` TEXT NOT NULL,'
            '   `prize_sharing` TEXT NOT NULL,'
            '   `is_main` INTEGER NOT NULL DEFAULT 0,'
            '   `index` INTEGER NOT NULL,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   UNIQUE(`id`),'
            '   FOREIGN KEY (`prize_group_id`) REFERENCES '
            '   `prize_group`(`id`) ON DELETE CASCADE'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `prize_criterion` ('
            '   `id` INTEGER NOT NULL,'
            '   `prize_category_id` INTEGER NOT NULL,'
            '   `type` TEXT NOT NULL,'
            '   `options` TEXT,'
            '   `index` INTEGER NOT NULL,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   UNIQUE(`id`),'
            '   FOREIGN KEY (`prize_category_id`) REFERENCES '
            '   `prize_category`(`id`) ON DELETE CASCADE'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `prize` ('
            '   `id` INTEGER NOT NULL,'
            '   `prize_category_id` INTEGER NOT NULL,'
            '   `value` FLOAT NOT NULL DEFAULT 0.0,'
            '   `is_monetary` INTEGER  NOT NULL DEFAULT 1,'
            '   `description` TEXT,'
            '   `index` INTEGER NOT NULL,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   UNIQUE(`id`),'
            '   FOREIGN KEY (`prize_category_id`) REFERENCES '
            '   `prize_category`(`id`) ON DELETE CASCADE'
            ')'
        )

    def backward(self):
        self.database.execute('DROP TABLE `prize_group`')
        self.database.execute('DROP TABLE `prize_category`')
        self.database.execute('DROP TABLE `prize_criterion`')
        self.database.execute('DROP TABLE `prize`')
