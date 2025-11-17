from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `player` ADD `k_standard` INTEGER')
        self.database.execute('ALTER TABLE `player` ADD `k_rapid` INTEGER')
        self.database.execute('ALTER TABLE `player` ADD `k_blitz` INTEGER')

    def backward(self):
        self.database.execute('ALTER TABLE `player` DROP COLUMN `k_standard`')
        self.database.execute('ALTER TABLE `player` DROP COLUMN `k_rapid`')
        self.database.execute('ALTER TABLE `player` DROP COLUMN `k_blitz`')
