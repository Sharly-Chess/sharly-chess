from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """The rating of the players no list rates, when no plugin prescribes
    one: ``info``.``unrated_rating`` for the event, NULL for the default,
    and ``tournament``.``unrated_rating`` for a tournament, NULL for the
    event's. An event that already has tournaments keeps ranking those
    players at 0."""

    def forward(self) -> None:
        self.database.execute('ALTER TABLE `info` ADD `unrated_rating` INTEGER')
        self.database.execute('ALTER TABLE `tournament` ADD `unrated_rating` INTEGER')
        self.database.execute(
            'UPDATE `info` SET `unrated_rating` = 0 '
            'WHERE EXISTS (SELECT 1 FROM `tournament`)'
        )

    def backward(self) -> None:
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `unrated_rating`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `unrated_rating`')
