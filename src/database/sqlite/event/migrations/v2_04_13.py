from database.sqlite.event.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self._execute(
            'ALTER TABLE `tournament` ADD `last_ffe_rules_upload` FLOAT'
        )
        self._execute(
            'UPDATE `tournament` SET `last_ffe_rules_upload` = 0.0'
        )
