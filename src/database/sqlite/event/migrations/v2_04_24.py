from database.sqlite.event.event_migration import AbstractEventMigration


class EventMigration(AbstractEventMigration):
    def forward(self):
        self.execute(
            'ALTER TABLE `tournament` DROP COLUMN `paired_bye_points`'
        )
        self.execute(
            'ALTER TABLE `tournament` ADD `paired_bye_result` INTEGER'
        )

    def backward(self):
        self.execute(
            'ALTER TABLE `tournament` ADD `paired_bye_points` FLOAT'
        )
        self.execute(
            'ALTER TABLE `tournament` DROP COLUMN `paired_bye_result`'
        )
