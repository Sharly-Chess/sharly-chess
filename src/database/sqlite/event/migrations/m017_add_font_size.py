from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `screen` ADD `font_size` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `family` ADD `font_size` INTEGER'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `screen` DROP COLUMN `font_size`'
        )
        self.database.execute(
            'ALTER TABLE `family` DROP COLUMN `font_size`'
        )
