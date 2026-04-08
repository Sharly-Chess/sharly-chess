from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `info` ADD `allow_multi_tournament_players` '
            'INTEGER NOT NULL DEFAULT 1'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `info` DROP COLUMN `allow_multi_tournament_players`'
        )
