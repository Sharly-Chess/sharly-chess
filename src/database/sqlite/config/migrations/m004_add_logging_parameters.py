from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `info` RENAME COLUMN `log_level` TO `console_log_level`'
        )
        self.database.execute('ALTER TABLE `info` ADD `console_color` INTEGER')
        self.database.execute('ALTER TABLE `info` ADD `console_show_date` INTEGER')
        self.database.execute('ALTER TABLE `info` ADD `console_show_level` INTEGER')
        self.database.execute('ALTER TABLE `info` ADD `experimental` INTEGER')

    def backward(self):
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `experimental`')
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `console_show_level`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `console_show_date`'
        )
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `console_color`')
        self.database.execute(
            'ALTER TABLE `info` RENAME COLUMN `console_log_level` TO `log_level`'
        )
