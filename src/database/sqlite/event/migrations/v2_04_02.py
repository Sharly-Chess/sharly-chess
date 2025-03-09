from database.sqlite.event.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self.execute('ALTER TABLE `screen` ADD `results_max_age` INTEGER')
        self.execute(
            'ALTER TABLE `info` DROP COLUMN `allow_results_deletion_on_input_screens`'
        )
