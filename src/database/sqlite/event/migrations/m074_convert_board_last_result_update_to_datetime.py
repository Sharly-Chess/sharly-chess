from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    # Add temporary TEXT column last_result_update_temp for datetime storage
    # Convert existing FLOAT timestamps to ISO-8601 UTC strings
    # - NULL and 0.0 (default/no result) → NULL
    # - Positive floats → 'YYYY-MM-DD HH:MM:SS' via datetime(ts, 'unixepoch')
    # Drop old FLOAT column
    # Rename last_result_update_temp column to last_result_update

    def forward(self):
        self.database.execute(
            'ALTER TABLE `board` ADD COLUMN `last_result_update_temp` TEXT'
        )

        self.database.execute(
            """UPDATE `board`
               SET `last_result_update_temp` =
                   CASE
                       WHEN `last_result_update` IS NOT NULL AND `last_result_update` > 0
                       THEN datetime(`last_result_update`, 'unixepoch')
                       ELSE NULL
                   END"""
        )

        self.database.execute('ALTER TABLE `board` DROP COLUMN `last_result_update`')

        self.database.execute(
            'ALTER TABLE `board` RENAME COLUMN `last_result_update_temp` TO `last_result_update`'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `board` ADD COLUMN `last_result_update_temp` REAL'
        )

        self.database.execute(
            """UPDATE `board`
               SET `last_result_update_temp` =
                   CASE
                       WHEN `last_result_update` IS NOT NULL
                       THEN CAST(strftime('%s', `last_result_update`) AS REAL)
                       ELSE 0.0
                   END"""
        )

        self.database.execute('ALTER TABLE `board` DROP COLUMN `last_result_update`')
        self.database.execute(
            'ALTER TABLE `board` RENAME COLUMN `last_result_update_temp` TO `last_result_update`'
        )
