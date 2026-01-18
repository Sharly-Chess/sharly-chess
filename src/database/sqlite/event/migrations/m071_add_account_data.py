from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `account` ADD `mail` TEXT')
        self.database.execute('ALTER TABLE `account` ADD `phone` TEXT')
        self.database.execute(
            "ALTER TABLE `account` ADD `plugin_data` TEXT NOT NULL DEFAULT '{}'"
        )

    def backward(self):
        self.database.execute('ALTER TABLE `account` DROP COLUMN `plugin_data`')
        self.database.execute('ALTER TABLE `account` DROP COLUMN `phone`')
        self.database.execute('ALTER TABLE `account` DROP COLUMN `mail`')
