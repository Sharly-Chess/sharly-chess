from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Let the arbiter mark players who are not eligible for voluntary byes
    (FIDE C.05:6.7.4)."""

    def forward(self) -> None:
        self.database.execute(
            'ALTER TABLE `player` ADD `byes_allowed` INTEGER NOT NULL DEFAULT 1'
        )

    def backward(self) -> None:
        self.database.execute('ALTER TABLE `player` DROP COLUMN `byes_allowed`')
