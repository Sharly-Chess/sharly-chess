from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Whether a list that also has an online source is read from it rather
    than from its installed copy, when players are added and their
    ratings checked."""

    def forward(self) -> None:
        self.database.execute(
            'ALTER TABLE `local_source_database` '
            'ADD `read_online` INTEGER NOT NULL DEFAULT 0'
        )

    def backward(self) -> None:
        self.database.execute(
            'ALTER TABLE `local_source_database` DROP COLUMN `read_online`'
        )
