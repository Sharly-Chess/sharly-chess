from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        for table in ('screen', 'family'):
            self.database.execute(
                f'ALTER TABLE `{table}` ADD `players_player_format` INT'
            )
            self.database.execute(
                f'ALTER TABLE `{table}` ADD `players_board_format` INT'
            )
            self.database.execute(
                f'ALTER TABLE `{table}` ADD `players_opponent_format` INT'
            )
            for params in {
                (1, 1, 1, 0),
                (4, 3, 5, 1),
            }:
                self.database.execute(
                    f'UPDATE `{table}` SET `players_player_format` = ?, `players_board_format` = ?, `players_opponent_format` = ? WHERE players_show_opponent = ?',
                    params,
                )
            self.database.execute(
                f'ALTER TABLE `{table}` DROP COLUMN `players_show_opponent`'
            )

    def backward(self):
        for table in ('family', 'screen'):
            self.database.execute(
                f'ALTER TABLE `{table}` ADD `players_show_opponent` INT'
            )
            self.database.execute(
                f'UPDATE `{table}` SET `players_show_opponent` = 1 WHERE `players_opponent_format` IS NOT NULL',
            )
            self.database.execute(
                f'UPDATE `{table}` SET `players_show_opponent` = 0 WHERE `players_opponent_format` = 1',
            )
            self.database.execute(
                f'ALTER TABLE `{table}` DROP COLUMN `players_opponent_format` INT'
            )
            self.database.execute(
                f'ALTER TABLE `{table}` DROP COLUMN `players_board_format` INT'
            )
            self.database.execute(
                f'ALTER TABLE `{table}` DROP COLUMN `players_player_format` INT'
            )
