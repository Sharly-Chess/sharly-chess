from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self) -> None:
        self.database.execute('ALTER TABLE `tournament` ADD `round_datetimes` TEXT')

    def backward(self) -> None:
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `round_datetimes`')
