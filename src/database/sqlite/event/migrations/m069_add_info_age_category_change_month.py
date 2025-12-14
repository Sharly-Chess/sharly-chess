from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `info` ADD `age_category_change_month` INTEGER DEFAULT 1'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `info` DROP COLUMN `age_category_change_month`'
        )
