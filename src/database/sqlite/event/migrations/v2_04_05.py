from database.sqlite.event.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self.execute('ALTER TABLE `rotator` DROP COLUMN `show_menus`')
