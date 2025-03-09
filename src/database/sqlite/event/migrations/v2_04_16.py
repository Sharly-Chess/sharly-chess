from database.sqlite.event.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self.execute('ALTER TABLE `info` ADD `message_text` TEXT')
        self.execute('ALTER TABLE `info` ADD `message_color` TEXT')
        self.execute(
            'ALTER TABLE `info` ADD `message_background_color` TEXT'
        )
        self.execute(
            'ALTER TABLE `screen` ADD `message_default` INTEGER NOT NULL DEFAULT 1'
        )
        self.execute('ALTER TABLE `screen` ADD `message_text` TEXT')
        self.execute(
            'ALTER TABLE `family` ADD `message_default` INTEGER NOT NULL DEFAULT 1'
        )
        self.execute('ALTER TABLE `family` ADD `message_text` TEXT')
        self.execute(
            'ALTER TABLE `rotator` ADD `message_default` INTEGER NOT NULL DEFAULT 1'
        )
        self.execute('ALTER TABLE `rotator` ADD `message_text` TEXT')
