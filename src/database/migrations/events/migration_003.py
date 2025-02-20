from database.sqlite.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self._execute('ALTER TABLE `rotator` DROP COLUMN `show_menus`')
