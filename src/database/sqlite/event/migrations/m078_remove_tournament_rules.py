from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `rules`')

    def backward(self):
        self.database.execute('ALTER TABLE `tournament` ADD `rules` TEXT')
