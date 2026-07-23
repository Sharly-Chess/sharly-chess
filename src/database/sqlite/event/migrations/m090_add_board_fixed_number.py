from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Freeze a board's fixed table number at pairing time."""

    def forward(self):
        self.database.execute('ALTER TABLE `board` ADD `fixed_number` INT')

    def backward(self):
        self.database.execute('ALTER TABLE `board` DROP COLUMN `fixed_number`')
