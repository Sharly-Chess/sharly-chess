from database.sqlite.event.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self.execute('ALTER TABLE `info` ADD `rules` TEXT')
        self.execute('ALTER TABLE `tournament` ADD `rules` TEXT')
