from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Freeze a board's fixed table number at pairing time, and let board
    screens/families choose how fixed boards are ordered (natural position vs
    board number)."""

    def forward(self):
        self.database.execute('ALTER TABLE `board` ADD `fixed_number` INT')
        self.database.execute('ALTER TABLE `screen_set` ADD `fixed_board_order` TEXT')
        self.database.execute('ALTER TABLE `family` ADD `fixed_board_order` TEXT')
        # A screen set that already lists board numbers keeps that behaviour:
        # its selection mode is "specific board numbers".
        self.database.execute(
            "UPDATE `screen_set` SET `fixed_board_order` = 'specific' "
            'WHERE `fixed_boards_str` IS NOT NULL'
        )

    def backward(self):
        self.database.execute('ALTER TABLE `family` DROP COLUMN `fixed_board_order`')
        self.database.execute(
            'ALTER TABLE `screen_set` DROP COLUMN `fixed_board_order`'
        )
        self.database.execute('ALTER TABLE `board` DROP COLUMN `fixed_number`')
