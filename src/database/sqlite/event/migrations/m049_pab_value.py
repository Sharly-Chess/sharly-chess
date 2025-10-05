from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `info` ADD `pab_value` INTEGER NOT NULL DEFAULT 3'
        )
        self.database.execute(
            'ALTER TABLE `info` ADD `three_points_for_a_win` INTEGER NOT NULL DEFAULT 0'
        )
        self.database.execute('ALTER TABLE `tournament` ADD `pab_value` INTEGER')

        # A temp column is required because of the NOT NULL constraint on the `three_points_for_a_win` column
        self.database.execute(
            'ALTER TABLE tournament ADD COLUMN tmp_three_points INTEGER;'
        )
        self.database.execute("""
            UPDATE tournament
            SET tmp_three_points = CASE
                WHEN three_points_for_a_win = 0 THEN NULL
                ELSE three_points_for_a_win
            END;
        """)
        self.database.execute(
            'ALTER TABLE tournament DROP COLUMN three_points_for_a_win;'
        )
        self.database.execute(
            'ALTER TABLE tournament RENAME COLUMN tmp_three_points TO three_points_for_a_win;'
        )

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `pab_value`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `three_points_for_a_win`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `pab_value`')

        self.database.execute(
            'ALTER TABLE tournament ADD COLUMN tmp_three_points INTEGER NOT NULL DEFAULT 0;'
        )

        self.database.execute("""
            UPDATE tournament
            SET tmp_three_points = COALESCE(three_points_for_a_win, 0);
        """)

        self.database.execute(
            'ALTER TABLE tournament DROP COLUMN three_points_for_a_win;'
        )
        self.database.execute(
            'ALTER TABLE tournament RENAME COLUMN tmp_three_points TO three_points_for_a_win;'
        )
