from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Replaces the tournament's `secondary_score` with a boolean."""

    def forward(self):
        self.database.execute(
            'ALTER TABLE `tournament` ADD `secondary_score_for_colours` '
            'INTEGER NOT NULL DEFAULT 1'
        )
        self.database.execute(
            'UPDATE `tournament` SET `secondary_score_for_colours` = 0 '
            'WHERE `secondary_score` IS NOT NULL '
            'AND `secondary_score` = `primary_score`'
        )
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `secondary_score`')

    def backward(self):
        self.database.execute('ALTER TABLE `tournament` ADD `secondary_score` TEXT')
        # Restore the old shape: the secondary is the other score, or the
        # primary itself when it was turned off.
        self.database.execute(
            'UPDATE `tournament` SET `secondary_score` = CASE '
            'WHEN `secondary_score_for_colours` = 0 THEN `primary_score` '
            "WHEN `primary_score` = 'GAME_POINTS' THEN 'MATCH_POINTS' "
            "ELSE 'GAME_POINTS' END"
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `secondary_score_for_colours`'
        )
