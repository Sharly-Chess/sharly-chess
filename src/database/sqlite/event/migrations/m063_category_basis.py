from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `info` ADD `age_category_base_date` TEXT')

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `age_category_base_date`')
