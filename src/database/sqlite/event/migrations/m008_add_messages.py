from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `info` ADD `message_text` TEXT')
        self.database.execute('ALTER TABLE `info` ADD `message_color` TEXT')
        self.database.execute(
            'ALTER TABLE `info` ADD `message_background_color` TEXT'
        )
        self.database.execute(
            'ALTER TABLE `screen` ADD `message_default` INTEGER NOT NULL DEFAULT 1'
        )
        self.database.execute('ALTER TABLE `screen` ADD `message_text` TEXT')
        self.database.execute(
            'ALTER TABLE `family` ADD `message_default` INTEGER NOT NULL DEFAULT 1'
        )
        self.database.execute('ALTER TABLE `family` ADD `message_text` TEXT')
        self.database.execute(
            'ALTER TABLE `rotator` ADD `message_default` INTEGER NOT NULL DEFAULT 1'
        )
        self.database.execute('ALTER TABLE `rotator` ADD `message_text` TEXT')
