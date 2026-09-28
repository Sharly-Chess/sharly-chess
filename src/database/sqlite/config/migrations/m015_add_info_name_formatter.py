from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self) -> None:
        self.database.execute(
            'ALTER TABLE `info` ADD `name_formatter` TEXT NOT NULL '
            "DEFAULT 'UPPER_LAST_FIRST'"
        )

    def backward(self) -> None:
        self.database.execute('ALTER TABLE `info` DROP COLUMN `name_formatter`')
