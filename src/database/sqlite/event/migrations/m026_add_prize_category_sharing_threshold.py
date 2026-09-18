from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self) -> None:
        self.database.execute(
            'ALTER TABLE `prize_category` ADD `sharing_threshold` FLOAT'
        )

    def backward(self) -> None:
        self.database.execute(
            'ALTER TABLE `prize_category` DROP COLUMN `sharing_threshold`'
        )
