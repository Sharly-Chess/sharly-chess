from database.sqlite.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self._execute(
            'ALTER TABLE `tournament` ADD `tie_breaks` TEXT'
        )
