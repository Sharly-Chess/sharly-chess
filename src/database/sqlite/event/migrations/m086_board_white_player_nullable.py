from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Relax ``board.white_player_id`` to nullable so a team-match
    board can store a hole on the physical white side (mirroring the
    already-nullable ``black_player_id``)."""

    @staticmethod
    def are_foreign_keys_enabled() -> bool:
        # ``pairing.board_id`` has ``ON DELETE CASCADE`` to ``board.id``;
        # with FK enforcement on, the table swap (DROP/RENAME) cascades
        # through and nukes every pairing row.
        return False

    def forward(self):
        # delete_board_on_pairing_delete (m038) references ``board``,
        # so it has to come down before the rename swap.
        self.database.execute('DROP TRIGGER IF EXISTS `delete_board_on_pairing_delete`')
        self.database.execute(
            'CREATE TABLE `board_new` ('
            '   `id` INTEGER NOT NULL,'
            '   `white_player_id` INTEGER,'
            '   `black_player_id` INTEGER,'
            '   `index` INTEGER NOT NULL,'
            '   `last_result_update` FLOAT,'
            '   `team_board_id` INTEGER,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`white_player_id`) REFERENCES '
            '   `player`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`black_player_id`) REFERENCES '
            '   `player`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`team_board_id`) REFERENCES '
            '   `team_board`(`id`) ON DELETE SET NULL'
            ')'
        )
        self.database.execute(
            'INSERT INTO `board_new` '
            '(`id`, `white_player_id`, `black_player_id`, '
            '`index`, `last_result_update`, `team_board_id`) '
            'SELECT `id`, `white_player_id`, `black_player_id`, '
            '`index`, `last_result_update`, `team_board_id` '
            'FROM `board`'
        )
        self.database.execute('DROP TABLE `board`')
        self.database.execute('ALTER TABLE `board_new` RENAME TO `board`')
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `delete_board_on_pairing_delete`
            AFTER DELETE ON `pairing`
            BEGIN
                DELETE FROM `board`
                WHERE `id` = `OLD`.`board_id`;
            END;
            """
        )

    def backward(self):
        self.database.execute('DROP TRIGGER IF EXISTS `delete_board_on_pairing_delete`')
        self.database.execute(
            'CREATE TABLE `board_new` ('
            '   `id` INTEGER NOT NULL,'
            '   `white_player_id` INTEGER NOT NULL,'
            '   `black_player_id` INTEGER,'
            '   `index` INTEGER NOT NULL,'
            '   `last_result_update` FLOAT,'
            '   `team_board_id` INTEGER,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`white_player_id`) REFERENCES '
            '   `player`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`black_player_id`) REFERENCES '
            '   `player`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`team_board_id`) REFERENCES '
            '   `team_board`(`id`) ON DELETE SET NULL'
            ')'
        )
        # Drop rows with NULL white_player_id — schema can't represent
        # them in the rolled-back world.
        self.database.execute(
            'INSERT INTO `board_new` '
            '(`id`, `white_player_id`, `black_player_id`, '
            '`index`, `last_result_update`, `team_board_id`) '
            'SELECT `id`, `white_player_id`, `black_player_id`, '
            '`index`, `last_result_update`, `team_board_id` '
            'FROM `board` WHERE `white_player_id` IS NOT NULL'
        )
        self.database.execute('DROP TABLE `board`')
        self.database.execute('ALTER TABLE `board_new` RENAME TO `board`')
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `delete_board_on_pairing_delete`
            AFTER DELETE ON `pairing`
            BEGIN
                DELETE FROM `board`
                WHERE `id` = `OLD`.`board_id`;
            END;
            """
        )
