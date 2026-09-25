from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Tournaments lasting more than 30 days, which FIDE rates one slice
    at a time.

    ``multi_period`` is the arbiter's flag and ``tournament_period`` holds
    the round each slice starts at; every tournament gets the single
    period covering all its rounds, so the read paths have one shape
    whatever its length. A slice is submitted as a tournament of its own,
    so it carries its own ``plugin_data``: a service that wants one
    registration per slice keeps that slice's identifiers there.

    A slice is played on the ratings and titles in force while it runs
    (FIDE B.01 1.1.4), so a player may hold different ones in each slice
    of a long tournament. The player's own columns keep the first of them
    — the rating C.07:10 asks tie-breaks for by default — and
    ``player_period`` records a slice where they differ.

    ``tie_break_rating`` is which of those a rating-based tie-break reads,
    which C.07:10 leaves to the arbiter when a player may hold more than
    one rating during the tournament."""

    def forward(self) -> None:
        self.database.execute(
            'ALTER TABLE `tournament` ADD `multi_period` INTEGER NOT NULL DEFAULT 0'
        )
        self.database.execute(
            "ALTER TABLE `tournament` ADD `tie_break_rating` TEXT NOT NULL DEFAULT ''"
        )
        self.database.execute(
            'CREATE TABLE `tournament_period` ('
            '   `id` INTEGER NOT NULL,'
            '   `tournament_id` INTEGER NOT NULL,'
            '   `first_round` INTEGER NOT NULL DEFAULT 1,'
            '   `plugin_data` TEXT,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`tournament_id`) REFERENCES '
            '   `tournament`(`id`) ON DELETE CASCADE,'
            '   UNIQUE(`tournament_id`, `first_round`)'
            ')'
        )
        self.database.execute(
            'INSERT INTO `tournament_period` (`tournament_id`, `first_round`) '
            'SELECT `id`, 1 FROM `tournament`'
        )
        self.database.execute(
            'CREATE TABLE `player_period` ('
            '   `id` INTEGER NOT NULL,'
            '   `player_id` INTEGER NOT NULL,'
            '   `period_id` INTEGER NOT NULL,'
            '   `ratings` TEXT,'
            "   `title` TEXT NOT NULL DEFAULT '',"
            "   `women_title` TEXT NOT NULL DEFAULT '',"
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`player_id`) REFERENCES '
            '   `player`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`period_id`) REFERENCES '
            '   `tournament_period`(`id`) ON DELETE CASCADE,'
            '   UNIQUE(`player_id`, `period_id`)'
            ')'
        )

    def backward(self) -> None:
        self.database.execute('DROP TABLE `player_period`')
        self.database.execute('DROP TABLE `tournament_period`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `tie_break_rating`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `multi_period`')
