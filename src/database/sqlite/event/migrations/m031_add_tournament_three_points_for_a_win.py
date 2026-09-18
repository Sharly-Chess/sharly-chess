from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self) -> None:
        self.database.execute(
            'ALTER TABLE `tournament` ADD `three_points_for_a_win` '
            'INTEGER NOT NULL DEFAULT 0'
        )

    def backward(self) -> None:
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `three_points_for_a_win`'
        )
