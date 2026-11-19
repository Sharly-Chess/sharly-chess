from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """The journal of the event: what was done, when and by whom.

    The entries point at the tournaments, players, boards and teams they are
    about without a foreign key, and hold the names they need in `data`: an
    entry outlives what it talks about, and still reads the way it did when
    it was written. The account the action was done from is kept the same
    way, so that deleting an account leaves the name of who acted.
    """

    def forward(self) -> None:
        self.database.execute(
            'CREATE TABLE `journal` ('
            '   `id` INTEGER NOT NULL,'
            '   `at` TEXT NOT NULL,'
            '   `action` TEXT NOT NULL,'
            '   `tournament_id` INTEGER,'
            '   `round` INTEGER,'
            '   `board_id` INTEGER,'
            '   `player_id` INTEGER,'
            '   `team_id` INTEGER,'
            '   `actor_kind` TEXT NOT NULL,'
            '   `actor_name` TEXT,'
            '   `account_id` INTEGER,'
            '   `host` TEXT,'
            '   `data` TEXT,'
            '   `text` TEXT,'
            '   PRIMARY KEY(`id` AUTOINCREMENT)'
            ')'
        )
        self.database.execute(
            'CREATE INDEX `journal_tournament` ON `journal` (`tournament_id`)'
        )

    def backward(self) -> None:
        self.database.execute('DROP TABLE `journal`')
