from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            "ALTER TABLE `info` ADD `plugin_data` TEXT NOT NULL DEFAULT '{}'"
        )
        self.database.execute(
            "ALTER TABLE `tournament` ADD `plugin_data` TEXT NOT NULL DEFAULT '{}'"
        )

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `plugin_data`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `plugin_data`')
