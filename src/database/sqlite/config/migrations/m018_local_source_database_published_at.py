from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """When the source published the copy of a list, where it tells: the
    version the ratings read from the copy record."""

    def forward(self) -> None:
        self.database.execute(
            'ALTER TABLE `local_source_database` ADD `published_at` REAL'
        )

    def backward(self) -> None:
        self.database.execute(
            'ALTER TABLE `local_source_database` DROP COLUMN `published_at`'
        )
