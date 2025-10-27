from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `plugin` RENAME COLUMN `is_enabled` TO `is_default_enabled`'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `plugin` RENAME COLUMN `is_default_enabled` TO `is_enabled`'
        )
