from database.sqlite.migration import AbstractMigration


class Migration(AbstractMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `family` ADD `ranking_crosstable` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `family` ADD `ranking_round` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `family` ADD `ranking_min_points` FLOAT'
        )
        self.database.execute(
            'ALTER TABLE `family` ADD `ranking_max_points` FLOAT'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `family` DROP COLUMN `ranking_crosstable`'
        )
        self.database.execute(
            'ALTER TABLE `family` DROP COLUMN `ranking_round`'
        )
        self.database.execute(
            'ALTER TABLE `family` DROP COLUMN `ranking_min_points`'
        )
        self.database.execute(
            'ALTER TABLE `family` DROP COLUMN `ranking_max_points`'
        )
