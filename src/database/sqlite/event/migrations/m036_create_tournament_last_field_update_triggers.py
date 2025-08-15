from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `last_result_update`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `last_illegal_move_update`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `last_check_in_update`'
        )

        # Pairing
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_pairing_update_on_pairing_insert`
            AFTER INSERT ON `pairing`
            BEGIN
                UPDATE `tournament` SET `last_pairing_update` = unixepoch()
                WHERE `id` = `NEW`.`tournament_id`;
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_pairing_update_on_pairing_update`
            AFTER UPDATE ON `pairing`
            BEGIN
                UPDATE `tournament` SET `last_pairing_update` = unixepoch()
                WHERE `id` = `NEW`.`tournament_id`;
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_pairing_update_on_pairing_delete`
            AFTER DELETE ON `pairing`
            BEGIN
                UPDATE `tournament` SET `last_pairing_update` = unixepoch()
                WHERE `id` = `OLD`.`tournament_id`;
            END;
            """
        )
        # Useful for board permutation or renumbering
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_pairing_update_on_board_update`
            AFTER UPDATE ON `board`
            BEGIN
                UPDATE `tournament` SET `last_pairing_update` = unixepoch()
                WHERE `id` = (
                    SELECT `tournament_id` FROM `pairing`
                    WHERE `board_id` = `NEW`.`id`
                    LIMIT 1
                );
            END;
            """
        )

        # Player
        # Trigger on player delete not needed as it is not yet related to any tournament_player
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_player_update_on_player_update`
            AFTER UPDATE ON `player`
            BEGIN
                UPDATE `tournament` SET `last_player_update` = unixepoch()
                WHERE `id` IN (
                    SELECT `tournament_id` FROM `tournament_player`
                    WHERE `player_id` = `NEW`.`id`
                );
            END;
            """
        )
        # Trigger on player delete not needed as it also deletes the tournament_player records
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_player_update_on_tournament_player_insert`
            AFTER INSERT ON `tournament_player`
            BEGIN
                UPDATE `tournament` SET `last_player_update` = unixepoch()
                WHERE `id` = `NEW`.`tournament_id`;
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_player_update_on_tournament_player_update`
            AFTER UPDATE ON `tournament_player`
            BEGIN
                UPDATE `tournament` SET `last_player_update` = unixepoch()
                WHERE `id` = `NEW`.`tournament_id`;
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_player_update_on_tournament_player_delete`
            AFTER DELETE ON `tournament_player`
            BEGIN
                UPDATE `tournament` SET `last_player_update` = unixepoch()
                WHERE `id` = `OLD`.`tournament_id`;
            END;
            """
        )

    def backward(self):
        for trigger in [
            'set_tournament_last_pairing_update_on_pairing_insert',
            'set_tournament_last_pairing_update_on_pairing_update',
            'set_tournament_last_pairing_update_on_pairing_delete',
            'set_tournament_last_pairing_update_on_board_update',
            'set_tournament_last_player_update_on_player_update',
            'set_tournament_last_player_update_on_tournament_player_insert',
            'set_tournament_last_player_update_on_tournament_player_update',
            'set_tournament_last_player_update_on_tournament_player_delete',
        ]:
            self.database.execute(f'DROP TRIGGER IF EXISTS `{trigger}`')

        self.database.execute(
            'ALTER TABLE `tournament` ADD COLUMN '
            '`last_result_update` FLOAT NOT NULL DEFAULT 0.0'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD COLUMN '
            '`last_illegal_move_update` FLOAT NOT NULL DEFAULT 0.0'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD COLUMN '
            '`last_check_in_update` FLOAT NOT NULL DEFAULT 0.0'
        )
