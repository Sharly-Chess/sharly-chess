from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Gives the players an identifier in their national federation, next to
    their FIDE id, with the data source the identifier comes from (which
    also tells the federation)."""

    def forward(self) -> None:
        self.database.execute('ALTER TABLE `player` ADD `national_id` TEXT')
        self.database.execute('ALTER TABLE `player` ADD `national_source` TEXT')

    def backward(self) -> None:
        self.database.execute('ALTER TABLE `player` DROP COLUMN `national_source`')
        self.database.execute('ALTER TABLE `player` DROP COLUMN `national_id`')
