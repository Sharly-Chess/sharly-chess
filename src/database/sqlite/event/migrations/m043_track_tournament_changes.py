from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        # Track that "something relevant" on a tournament changed
        # (last_pairing_update, last_player_update, or last_update)
        self.database.execute('ALTER TABLE `tournament` ADD `dirty` BOOLEAN DEFAULT 0')

        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `mark_tournament_dirty_on_relevant_update`
            AFTER UPDATE OF `last_pairing_update`, `last_player_update`, `last_update` ON `tournament`
            WHEN (NEW.`last_pairing_update` IS NOT OLD.`last_pairing_update`)
              OR (NEW.`last_player_update`  IS NOT OLD.`last_player_update`)
              OR (NEW.`last_update`         IS NOT OLD.`last_update`)
            BEGIN
                UPDATE `tournament`
                    SET `dirty` = 1
                    WHERE `id` = NEW.`id`;
            END;
            """
        )

    def backward(self):
        self.database.execute(
            'DROP TRIGGER IF EXISTS `mark_tournament_dirty_on_relevant_update`'
        )
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `dirty`')
