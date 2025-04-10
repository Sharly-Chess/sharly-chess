from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `info` ADD `location` TEXT')
        self.database.execute('ALTER TABLE `info` ADD `arbiter` TEXT')
        self.database.execute(
            'ALTER TABLE `tournament` ADD `rounds` INTEGER NOT NULL DEFAULT 1'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `rating` INTEGER NOT NULL DEFAULT 1'
        )

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `location`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `arbiter`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `rating`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `rounds`')
