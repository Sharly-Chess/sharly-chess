from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Adds the theme of the administration: `auto`, which follows the
    appearance of the system, `dark` or `light`."""

    def forward(self) -> None:
        self.database.execute(
            "ALTER TABLE `info` ADD `admin_theme` TEXT NOT NULL DEFAULT 'auto'"
        )

    def backward(self) -> None:
        self.database.execute('ALTER TABLE `info` DROP COLUMN `admin_theme`')
