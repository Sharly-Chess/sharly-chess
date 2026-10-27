from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self) -> None:
        self.database.execute(
            "ALTER TABLE `info` ADD `name_formatter` TEXT NOT NULL DEFAULT 'LAST_FIRST'"
        )
        self.database.execute(
            'ALTER TABLE `info` ADD `capitalise_last_name` INTEGER NOT NULL DEFAULT 1'
        )

    def backward(self) -> None:
        self.database.execute('ALTER TABLE `info` DROP COLUMN `capitalise_last_name`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `name_formatter`')
