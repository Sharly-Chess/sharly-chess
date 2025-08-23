from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        # When a tournament player is deleted,
        # also delete the player if it is not linked to any other tournament player
        # This prevents having players associated with no tournament
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `delete_player_on_tournament_player_delete`
            AFTER DELETE ON `tournament_player`
            BEGIN
                DELETE FROM `player`
                WHERE `id` = `OLD`.`player_id` AND (
                    SELECT COUNT(*) FROM `tournament_player`
                    WHERE `player_id` = `OLD`.`player_id`
                ) = 0;
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `delete_pairing_on_tournament_player_delete`
            AFTER DELETE ON `tournament_player`
            BEGIN
                DELETE FROM `pairing`
                WHERE `player_id` = `OLD`.`player_id`
                AND `tournament_id` = `OLD`.`tournament_id`;
            END;
            """
        )
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
        self.database.execute(
            'DROP TRIGGER IF EXISTS `delete_player_on_tournament_player_delete`'
        )
        self.database.execute(
            'DROP TRIGGER IF EXISTS `delete_pairing_on_tournament_player_delete`'
        )
        self.database.execute('DROP TRIGGER IF EXISTS `delete_board_on_pairing_delete`')
