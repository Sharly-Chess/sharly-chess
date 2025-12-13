from pathlib import Path

from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('SELECT * FROM `info`')
        row = self.database.fetchone()
        rules = row['rules']
        if rules and Path(rules).exists():
            self.database.execute(
                'UPDATE `tournament` SET `rules` = ? WHERE `rules` IS NULL',
                (row['rules'],),
            )
        self.database.execute(
            'UPDATE `tournament` SET `record_illegal_moves` = ? '
            'WHERE `record_illegal_moves` IS NULL',
            (row['record_illegal_moves'],),
        )
        self.database.execute(
            'UPDATE `tournament` SET `override_unrated_rapid_blitz` = ? '
            'WHERE `override_unrated_rapid_blitz` IS NULL',
            (row['override_unrated_rapid_blitz'] or 0,),
        )
        self.database.execute(
            'UPDATE `tournament` SET `three_points_for_a_win` = ? '
            'WHERE `three_points_for_a_win` IS NULL',
            (row['three_points_for_a_win'],),
        )
        self.database.execute(
            'UPDATE `tournament` SET `pab_value` = ? WHERE `pab_value` IS NULL',
            (row['pab_value'],),
        )
        self.database.execute('ALTER TABLE `info` DROP COLUMN `rules`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `record_illegal_moves`')
        self.database.execute(
            'ALTER TABLE `info` DROP COLUMN `override_unrated_rapid_blitz`'
        )
        self.database.execute('ALTER TABLE `info` DROP COLUMN `three_points_for_a_win`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `pab_value`')

    def backward(self):
        self.database.execute('ALTER TABLE `info` ADD COLUMN `rules` TEXT')
        self.database.execute(
            'ALTER TABLE `info` ADD COLUMN `record_illegal_moves` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `info` ADD COLUMN `override_unrated_rapid_blitz` '
            'INTEGER NOT NULL DEFAULT 1'
        )
        self.database.execute(
            'ALTER TABLE `info` ADD COLUMN `three_points_for_a_win`'
            ' INTEGER NOT NULL DEFAULT 0'
        )
        self.database.execute(
            'ALTER TABLE `info` ADD COLUMN `pab_value` INTEGER NOT NULL DEFAULT 3'
        )
