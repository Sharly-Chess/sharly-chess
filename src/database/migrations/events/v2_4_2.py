from database.sqlite.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self._execute('ALTER TABLE `screen` ADD `results_max_age` INTEGER')
        self._execute(
            'ALTER TABLE `info` DROP COLUMN `allow_results_deletion_on_input_screens`'
        )
