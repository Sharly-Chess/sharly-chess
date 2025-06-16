from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `info` ADD `prize_currency` TEXT')
        self.database.execute("UPDATE `info` SET `prize_currency` = 'EUR'")

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `prize_currency`')
