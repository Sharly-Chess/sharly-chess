from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Manual bonus / penalty points for a player in an individual
    tournament — the counterpart of `team_point_adjustment`. A single
    delta, because individual tournaments score in game points only."""

    def forward(self):
        self.database.execute(
            'CREATE TABLE `player_point_adjustment` ('
            '   `id` INTEGER NOT NULL,'
            '   `tournament_id` INTEGER NOT NULL,'
            '   `player_id` INTEGER NOT NULL,'
            '   `round` INTEGER NOT NULL,'
            '   `delta` REAL NOT NULL DEFAULT 0,'
            '   `reason` TEXT,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`tournament_id`) REFERENCES '
            '   `tournament`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`player_id`) REFERENCES '
            '   `player`(`id`) ON DELETE CASCADE,'
            '   UNIQUE(`tournament_id`, `player_id`, `round`)'
            ')'
        )

    def backward(self):
        self.database.execute('DROP TABLE `player_point_adjustment`')
