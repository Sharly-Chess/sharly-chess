from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self) -> None:
        self.database.execute('ALTER TABLE `info` ADD `organiser_director` TEXT')

    def backward(self) -> None:
        self.database.execute('ALTER TABLE `info` DROP COLUMN `organiser_director`')
