from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `info` ADD `override_unrated_rapide_blitz` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `override_unrated_rapide_blitz` INTEGER'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `info` DROP COLUMN `override_unrated_rapide_blitz`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `override_unrated_rapide_blitz`'
        )
