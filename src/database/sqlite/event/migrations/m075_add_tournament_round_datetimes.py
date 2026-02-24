from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `tournament` ADD `round_datetimes` TEXT')

    def backward(self):
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `round_datetimes`')
