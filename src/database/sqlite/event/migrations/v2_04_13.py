from database.sqlite.event.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self.execute(
            'ALTER TABLE `tournament` ADD `last_ffe_rules_upload` FLOAT'
        )
        self.execute(
            'UPDATE `tournament` SET `last_ffe_rules_upload` = 0.0'
        )
