from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        # Add the new time_control_trf25 column
        self.database.execute('ALTER TABLE `tournament` ADD `time_control_trf25` TEXT')

        # Populate the new field with existing data
        # Format: <initial>+<increment> or just <initial> if increment is 0/null
        self.database.execute("""
            UPDATE `tournament`
            SET `time_control_trf25` =
                CASE
                    WHEN `time_control_initial_time` IS NULL THEN NULL
                    WHEN `time_control_increment` IS NULL OR `time_control_increment` = 0 THEN
                        CAST(`time_control_initial_time` AS TEXT)
                    ELSE
                        CAST(`time_control_initial_time` AS TEXT) || '+' || CAST(`time_control_increment` AS TEXT)
                END
        """)

        # Drop the old columns
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `time_control_initial_time`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `time_control_increment`'
        )

    def backward(self):
        # Add back the original columns
        self.database.execute(
            'ALTER TABLE `tournament` ADD `time_control_initial_time` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `time_control_increment` INTEGER'
        )

        # Drop the trf25 column
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `time_control_trf25`'
        )
