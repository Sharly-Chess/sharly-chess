from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `background_image`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `hide_background_image`')

    def backward(self):
        self.database.execute('ALTER TABLE `info` ADD `background_image` TEXT')
        self.database.execute(
            'ALTER TABLE `info` ADD `hide_background_image` INTEGER DEFAULT 0'
        )
