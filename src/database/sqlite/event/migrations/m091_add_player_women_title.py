from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Splits the single `title` field into an open title (`title`) and a
    women title (`women_title`). Historic women titles were stored in `title`,
    so they are relocated to the new column."""

    WOMEN_TITLES: tuple[str, ...] = ('WCM', 'WFM', 'WIM', 'WGM')

    def forward(self):
        self.database.execute(
            "ALTER TABLE `player` ADD `women_title` TEXT NOT NULL DEFAULT ''"
        )
        placeholders = ', '.join('?' for _ in self.WOMEN_TITLES)
        self.database.execute(
            f"UPDATE `player` SET `women_title` = `title`, `title` = '' "
            f'WHERE `title` IN ({placeholders})',
            self.WOMEN_TITLES,
        )

    def backward(self):
        # Restore the women title into `title` only when no open title is set.
        self.database.execute(
            'UPDATE `player` SET `title` = `women_title` '
            "WHERE `title` = '' AND `women_title` != ''"
        )
        self.database.execute('ALTER TABLE `player` DROP COLUMN `women_title`')
