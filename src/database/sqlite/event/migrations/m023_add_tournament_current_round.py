from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self) -> None:
        self.database.execute('ALTER TABLE `tournament` ADD `current_round` INTEGER')

    def backward(self) -> None:
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `current_round`')
