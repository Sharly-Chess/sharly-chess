from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `tournament_player` ADD `manual_tiebreak` INTEGER'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `tournament_player` DROP COLUMN `manual_tiebreak`'
        )
