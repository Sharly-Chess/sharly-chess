from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Lists that also have an online source read it before their installed
    copy, on every existing list and on those added later."""

    def _replace_column(self, default: int) -> None:
        self.database.execute(
            'ALTER TABLE `local_source_database` DROP COLUMN `read_online`'
        )
        self.database.execute(
            'ALTER TABLE `local_source_database` '
            f'ADD `read_online` INTEGER NOT NULL DEFAULT {default}'
        )

    def forward(self) -> None:
        self._replace_column(default=1)

    def backward(self) -> None:
        self._replace_column(default=0)
