from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        # Reset player check-in status of tournaments with the check-in closed
        self.database.execute(
            'UPDATE player SET check_in = 1 WHERE ('
            '   SELECT t.check_in_open = 0 FROM tournament AS t '
            '   INNER JOIN tournament_player AS tp ON t.id = tournament_id'
            '   WHERE player.id = tp.player_id'
            ')'
        )
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `check_in_open`')

    def backward(self):
        self.database.execute(
            'ALTER TABLE `tournament` ADD `check_in_open` INTEGER NOT NULL DEFAULT 0'
        )
