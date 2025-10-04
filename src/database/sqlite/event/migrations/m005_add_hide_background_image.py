from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `info` ADD `hide_background_image` INTEGER')
        self.database.execute(
            'UPDATE `info` SET `hide_background_image` = 0',
        )
