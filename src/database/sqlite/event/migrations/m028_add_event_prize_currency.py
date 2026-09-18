from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self) -> None:
        self.database.execute('ALTER TABLE `info` ADD `prize_currency` TEXT')

    def backward(self) -> None:
        self.database.execute('ALTER TABLE `info` DROP COLUMN `prize_currency`')
