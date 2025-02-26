from database.sqlite.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self._execute(
            'ALTER TABLE `tournament` ADD `first_board_number` INTEGER'
        )
        self._execute(
            'ALTER TABLE `tournament` ADD `paired_bye_points` FLOAT'
        )
        self._execute(
            'ALTER TABLE `tournament` ADD `max_byes` INTEGER'
        )
        self._execute(
            'ALTER TABLE `tournament` ADD `last_rounds_no_byes` INTEGER'
        )
        # Drop table chessevent since the SQL code of the creation of the table
        # had been left by error in create_event.sql
        self._execute('DROP TABLE IF EXISTS `chessevent`')
