from database.sqlite.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self._execute(
            """ALTER TABLE `tournament` ADD `point_values` TEXT DEFAULT '{ "0": 0, "1": 1, "=": 0.5 }'"""
        )

    def backward(self):
        self._execute(
            'ALTER TABLE `tournament` DROP COLUMN `point_values`'
        )
