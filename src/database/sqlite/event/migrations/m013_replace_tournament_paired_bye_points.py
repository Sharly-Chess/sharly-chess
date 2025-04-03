from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `paired_bye_points`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `paired_bye_result` INTEGER'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `tournament` ADD `paired_bye_points` FLOAT'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `paired_bye_result`'
        )
