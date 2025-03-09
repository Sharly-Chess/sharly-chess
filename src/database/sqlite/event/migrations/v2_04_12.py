from database.sqlite.event.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self._execute('ALTER TABLE `info` ADD `rules` TEXT')
        self._execute('ALTER TABLE `tournament` ADD `rules` TEXT')
