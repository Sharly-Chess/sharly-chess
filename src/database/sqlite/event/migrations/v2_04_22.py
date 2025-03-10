from database.sqlite.migration import AbstractMigration


class Migration(AbstractMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `tournament` ADD `first_board_number` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `paired_bye_points` FLOAT'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `max_byes` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `last_rounds_no_byes` INTEGER'
        )
        # Drop table chessevent since the SQL code of the creation of the table
        # had been left by error in create_event.sql
        self.database.execute('DROP TABLE IF EXISTS `chessevent`')

    def backward(self):
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `first_board_number`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `paired_bye_points`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `max_byes`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `last_rounds_no_byes`'
        )
