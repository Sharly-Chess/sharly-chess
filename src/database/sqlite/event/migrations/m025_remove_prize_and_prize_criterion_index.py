from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `prize` DROP COLUMN `index`')
        self.database.execute('ALTER TABLE `prize_criterion` DROP COLUMN `index`')

    def backward(self):
        self.database.execute(
            'ALTER TABLE `prize` ADD `index` INTEGER NOT NULL DEFAULT 0'
        )
        self.database.execute(
            'ALTER TABLE `prize_criterion` ADD `index` INTEGER NOT NULL DEFAULT 0'
        )
