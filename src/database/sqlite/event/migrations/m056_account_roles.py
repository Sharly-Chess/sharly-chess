from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `account` ADD `fide_id` INTEGER')

    def backward(self):
        self.database.execute('ALTER TABLE `account` DROP COLUMN `fide_id`')
