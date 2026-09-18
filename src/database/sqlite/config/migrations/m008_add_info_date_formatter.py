from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self) -> None:
        self.database.execute(
            "ALTER TABLE `info` ADD `date_formatter` TEXT NOT NULL DEFAULT 'ISO'"
        )
        self.database.execute('UPDATE `info` SET `force_edit` = 1')

    def backward(self) -> None:
        self.database.execute('ALTER TABLE `info` DROP COLUMN `date_formatter`')
