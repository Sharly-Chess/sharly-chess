from database.sqlite.event.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self._execute(
            'ALTER TABLE `tournament` ADD `check_in_open` INTEGER NOT NULL DEFAULT 0'
        )
