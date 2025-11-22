from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `info` ADD `organiser_name` TEXT')
        self.database.execute('ALTER TABLE `info` ADD `organiser_home_page` TEXT')
        self.database.execute('ALTER TABLE `info` ADD `organiser_email` TEXT')

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `organiser_email`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `organiser_home_page`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `organiser_name`')
