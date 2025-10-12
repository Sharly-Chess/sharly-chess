from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            "ALTER TABLE `plugin` ADD `plugin_data` TEXT NOT NULL DEFAULT '{}'"
        )

    def backward(self):
        self.database.execute('ALTER TABLE `plugin` DROP COLUMN `plugin_data`')
