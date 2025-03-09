from database.sqlite.event.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self._execute('ALTER TABLE `info` ADD `message_text` TEXT')
        self._execute('ALTER TABLE `info` ADD `message_color` TEXT')
        self._execute(
            'ALTER TABLE `info` ADD `message_background_color` TEXT'
        )
        self._execute(
            'ALTER TABLE `screen` ADD `message_default` INTEGER NOT NULL DEFAULT 1'
        )
        self._execute('ALTER TABLE `screen` ADD `message_text` TEXT')
        self._execute(
            'ALTER TABLE `family` ADD `message_default` INTEGER NOT NULL DEFAULT 1'
        )
        self._execute('ALTER TABLE `family` ADD `message_text` TEXT')
        self._execute(
            'ALTER TABLE `rotator` ADD `message_default` INTEGER NOT NULL DEFAULT 1'
        )
        self._execute('ALTER TABLE `rotator` ADD `message_text` TEXT')
