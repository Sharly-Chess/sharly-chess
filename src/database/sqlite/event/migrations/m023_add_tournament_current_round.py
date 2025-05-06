from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `tournament` ADD `current_round` INTEGER')

    def backward(self):
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `current_round`')
