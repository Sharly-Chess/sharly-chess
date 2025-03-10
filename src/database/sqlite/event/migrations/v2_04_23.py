from database.sqlite.migration import AbstractMigration


class Migration(AbstractMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `tournament` ADD `tie_breaks` TEXT'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `tie_breaks`'
        )
