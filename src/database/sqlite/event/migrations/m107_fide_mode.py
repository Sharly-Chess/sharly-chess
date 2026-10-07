from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """FIDE mode, per tournament, and the log of the pairing integrity
    breaching events (PIBEs).

    Existing tournaments start in FIDE mode: only the systems that support it
    read the flag. The round FIDE mode was left at is kept for the TRF, and
    the round whose pairings are being edited by hand, until they are
    checked, with its boards as they were before, to put them back.

    A game found wrong too late to change the round it was played in is
    corrected for the rating report only: the colours and the result
    recorded for it there."""

    def forward(self) -> None:
        self.database.execute(
            'ALTER TABLE `tournament` ADD `fide_mode` INTEGER NOT NULL DEFAULT 1'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `fide_mode_exit_round` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `manual_pairing_round` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `manual_pairing_boards` TEXT'
        )
        self.database.execute(
            'CREATE TABLE `pibe` ('
            '   `id` INTEGER NOT NULL,'
            '   `tournament_id` INTEGER NOT NULL,'
            '   `round` INTEGER NOT NULL,'
            '   `type` TEXT NOT NULL,'
            '   `description` TEXT NOT NULL,'
            '   `members` TEXT,'
            '   `date` TEXT NOT NULL,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`tournament_id`) REFERENCES '
            '   `tournament`(`id`) ON DELETE CASCADE'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `rating_correction` ('
            '   `id` INTEGER NOT NULL,'
            '   `tournament_id` INTEGER NOT NULL,'
            '   `round` INTEGER NOT NULL,'
            '   `white_player_id` INTEGER NOT NULL,'
            '   `black_player_id` INTEGER NOT NULL,'
            '   `result` INTEGER NOT NULL,'
            '   `date` TEXT NOT NULL,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`tournament_id`) REFERENCES '
            '   `tournament`(`id`) ON DELETE CASCADE'
            ')'
        )

    def backward(self) -> None:
        self.database.execute('DROP TABLE `rating_correction`')
        self.database.execute('DROP TABLE `pibe`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `fide_mode`')
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `fide_mode_exit_round`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `manual_pairing_round`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `manual_pairing_boards`'
        )
