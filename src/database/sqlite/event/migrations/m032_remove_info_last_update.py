from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self) -> None:
        self.database.execute('ALTER TABLE `info` DROP COLUMN `last_update`')

    def backward(self) -> None:
        self.database.execute(
            'ALTER TABLE `info` ADD `last_update` FLOAT NOT NULL DEFAULT 0.0'
        )
