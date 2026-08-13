from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Makes the points an explicit ranking criterion."""

    def forward(self):
        # Free up index 0 across every tournament, then take it.
        self.database.execute('UPDATE `tie_break` SET `index` = `index` + 1')
        self.database.execute(
            'INSERT INTO `tie_break` (`tournament_id`, `type`, `options`, `index`) '
            "SELECT `id`, 'POINTS', '{}', 0 FROM `tournament`"
        )

    def backward(self):
        self.database.execute("DELETE FROM `tie_break` WHERE `type` = 'POINTS'")
        # Close the gap left at the front. Tournaments that had no
        # POINTS entry are unaffected: their indexes are already
        # contiguous from 0, and shifting down would break them.
        self.database.execute(
            'UPDATE `tie_break` SET `index` = `index` - 1 '
            'WHERE `tournament_id` IN ('
            '   SELECT `tournament_id` FROM `tie_break` GROUP BY `tournament_id` '
            '   HAVING MIN(`index`) > 0'
            ')'
        )
