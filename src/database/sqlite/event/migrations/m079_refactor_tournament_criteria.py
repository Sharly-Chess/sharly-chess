from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            "ALTER TABLE `tournament` ADD `criteria` TEXT NOT NULL DEFAULT '{}'"
        )
        self.database.execute('DROP TABLE `tournament_criterion`')
        self.database.execute(
            'DELETE FROM `prize_criterion` WHERE `type` = ?', ('ffe-LICENCE',)
        )

    def backward(self):
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `criteria`')
        self.database.execute(
            'CREATE TABLE `tournament_criterion` ('
            '   `id` INTEGER NOT NULL,'
            '   `tournament_id` INTEGER NOT NULL,'
            '   `type` TEXT NOT NULL,'
            '   `options` TEXT,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   UNIQUE(`id`),'
            '   FOREIGN KEY (`tournament_id`) REFERENCES '
            '   `tournament`(`id`) ON DELETE CASCADE'
            ')'
        )
