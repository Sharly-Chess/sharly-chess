from database.sqlite.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self._execute(
            'ALTER TABLE `screen` ADD `input_exit_button` INTEGER'
        )
        self._execute(
            'ALTER TABLE `family` ADD `input_exit_button` INTEGER'
        )
