from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `last_update`')

    def backward(self):
        self.database.execute(
            'ALTER TABLE `info` ADD `last_update` FLOAT NOT NULL DEFAULT 0.0'
        )
