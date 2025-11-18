from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `info` ADD `organiser_name` INTEGER')
        self.database.execute('ALTER TABLE `info` ADD `organiser_home_page` INTEGER')
        self.database.execute('ALTER TABLE `info` ADD `organiser_email` INTEGER')

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `organiser_email`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `organiser_home_page`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `organiser_name`')
