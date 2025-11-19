from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `info` ADD `organiser_director` INTEGER')

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `organiser_director`')
