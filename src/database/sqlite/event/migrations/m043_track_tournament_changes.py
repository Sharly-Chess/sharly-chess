from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        # Track that "something relevant" on a tournament changed
        # (last_pairing_update, last_player_update, or last_update)
        self.database.execute(
            """
            CREATE TABLE IF NOT EXISTS `tournament_dirty` (
                `tournament_id` INTEGER PRIMARY KEY,
                `dirty`         INTEGER NOT NULL DEFAULT 0,
                `last_touch_ts` INTEGER,
                FOREIGN KEY(`tournament_id`) REFERENCES `tournament`(`id`) ON DELETE CASCADE
            );
            """
        )

        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `mark_tournament_dirty_on_relevant_update`
            AFTER UPDATE OF `last_pairing_update`, `last_player_update`, `last_update` ON `tournament`
            WHEN (NEW.`last_pairing_update` IS NOT OLD.`last_pairing_update`)
              OR (NEW.`last_player_update`  IS NOT OLD.`last_player_update`)
              OR (NEW.`last_update`         IS NOT OLD.`last_update`)
            BEGIN
                INSERT INTO `tournament_dirty`(`tournament_id`, `dirty`, `last_touch_ts`)
                VALUES (NEW.`id`, 1, unixepoch())
                ON CONFLICT(`tournament_id`) DO UPDATE
                    SET `dirty` = 1,
                        `last_touch_ts` = excluded.`last_touch_ts`;
            END;
            """
        )

    def backward(self):
        self.database.execute(
            'DROP TRIGGER IF EXISTS `mark_tournament_dirty_on_relevant_update`'
        )
        self.database.execute('DROP TABLE IF EXISTS `tournament_dirty`')
