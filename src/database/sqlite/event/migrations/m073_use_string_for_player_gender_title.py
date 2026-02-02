from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    GENDER_MAPPING: dict[int, str] = {
        0: '',
        1: 'F',
        2: 'M',
    }
    TITLE_MAPPING: dict[int, str] = {
        0: '',
        1: 'WCM',
        2: 'CM',
        3: 'WFM',
        4: 'FM',
        5: 'WIM',
        6: 'IM',
        7: 'WGM',
        8: 'GM',
    }
    MAPPING_BY_PLAYER_COLUMN: dict[str, dict[int, str]] = {
        'gender': GENDER_MAPPING,
        'title': TITLE_MAPPING,
    }

    def forward(self):
        for column, mapping in self.MAPPING_BY_PLAYER_COLUMN.items():
            self.database.execute(
                f'ALTER TABLE `player` RENAME COLUMN `{column}` TO `{column}_int`'
            )
            self.database.execute(f'ALTER TABLE `player` ADD `{column}` TEXT')
            for int_value, str_value in mapping.items():
                self.database.execute(
                    f'UPDATE `player` SET `{column}` = ? WHERE `{column}_int` = ?',
                    (str_value, int_value),
                )
            self.database.execute(f'ALTER TABLE `player` DROP COLUMN `{column}_int`')

        for prefix in ('tournament', 'prize'):
            for int_value, str_value in self.GENDER_MAPPING.items():
                self.database.execute(
                    f'UPDATE `{prefix}_criterion` '
                    "SET `options` = JSON_SET(options, '$.GENDER_VALUE', ?) "
                    "WHERE JSON_EXTRACT(options, '$.GENDER_VALUE') = ?;",
                    (str_value, int_value),
                )

    def backward(self):
        for column, mapping in self.MAPPING_BY_PLAYER_COLUMN.items():
            self.database.execute(
                f'ALTER TABLE `player` RENAME COLUMN `{column}` TO `{column}_str`'
            )
            self.database.execute(f'ALTER TABLE `player` ADD `{column}` INTEGER')
            for int_value, str_value in mapping.items():
                self.database.execute(
                    f'UPDATE `player` SET `{column}` = ? WHERE `{column}_str` = ?',
                    (int_value, str_value),
                )
            self.database.execute(f'ALTER TABLE `player` DROP COLUMN `{column}_str`')

        for prefix in ('tournament', 'prize'):
            for int_value, str_value in self.GENDER_MAPPING.items():
                self.database.execute(
                    f'UPDATE `{prefix}_criterion` '
                    "SET `options` = JSON_SET(options, '$.GENDER_VALUE', ?) "
                    "WHERE JSON_EXTRACT(options, '$.GENDER_VALUE') = ?;",
                    (int_value, str_value),
                )
