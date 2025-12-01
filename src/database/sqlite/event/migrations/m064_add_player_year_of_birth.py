from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `player` ADD COLUMN `year_of_birth` INTEGER')

    def backward(self):
        self.database.execute(
            'UPDATE `player` SET `date_of_birth` = `year_of_birth` || ? '
            'WHERE `year_of_birth` IS NOT NULL AND `date_of_birth` IS NOT NULL',
            ('-01-01',),
        )
        self.database.execute('ALTER TABLE `player` DROP COLUMN `year_of_birth`')
