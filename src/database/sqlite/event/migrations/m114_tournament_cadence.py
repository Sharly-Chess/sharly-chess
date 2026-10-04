from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """The time control a tournament is played at, which decides the
    ratings in play, is its cadence."""

    def forward(self) -> None:
        self.database.execute(
            'ALTER TABLE `tournament` RENAME COLUMN `rating` TO `cadence`'
        )

    def backward(self) -> None:
        self.database.execute(
            'ALTER TABLE `tournament` RENAME COLUMN `cadence` TO `rating`'
        )
