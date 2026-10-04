from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """The automatic check of the players' ratings against the rating
    lists, which the arbiter may switch off (VCL Q138), and the snapshots
    of the lists the arbiter last dismissed its findings for."""

    def forward(self) -> None:
        self.database.execute(
            'ALTER TABLE `info` ADD `check_ratings` INTEGER NOT NULL DEFAULT 1'
        )
        self.database.execute(
            "ALTER TABLE `info` ADD `ratings_check_dismissed` TEXT NOT NULL DEFAULT ''"
        )

    def backward(self) -> None:
        self.database.execute(
            'ALTER TABLE `info` DROP COLUMN `ratings_check_dismissed`'
        )
        self.database.execute('ALTER TABLE `info` DROP COLUMN `check_ratings`')
