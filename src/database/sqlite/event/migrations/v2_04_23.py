from database.sqlite.event.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self._execute(
            'ALTER TABLE `tournament` ADD `tie_breaks` TEXT'
        )

    def backward(self):
        self._execute(
            'ALTER TABLE `tournament` DROP COLUMN `tie_breaks`'
        )
