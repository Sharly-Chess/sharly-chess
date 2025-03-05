from database.sqlite.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self._execute(
            'ALTER TABLE `tournament` DROP COLUMN `paired_bye_points`'
        )
        self._execute(
            'ALTER TABLE `tournament` ADD `paired_bye_result` INTEGER'
        )

    def backward(self):
        self._execute(
            'ALTER TABLE `tournament` ADD `paired_bye_points` FLOAT'
        )
        self._execute(
            'ALTER TABLE `tournament` DROP COLUMN `paired_bye_result`'
        )
