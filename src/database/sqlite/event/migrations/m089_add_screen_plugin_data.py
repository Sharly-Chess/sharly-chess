from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self) -> None:
        self.database.execute('ALTER TABLE `screen` ADD `plugin_data` TEXT')

    def backward(self) -> None:
        self.database.execute('ALTER TABLE `screen` DROP COLUMN `plugin_data`')
