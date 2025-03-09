from database.sqlite.event.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self.execute(
            'ALTER TABLE `screen` ADD `input_exit_button` INTEGER'
        )
        self.execute(
            'ALTER TABLE `family` ADD `input_exit_button` INTEGER'
        )
