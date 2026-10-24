from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Where the event came from, and when.

    Restoring a backup beside an event leaves two events holding almost the
    same thing, and nothing on the screen told them apart. The events that
    already exist carry no origin: what they came from was not recorded when
    it happened and cannot be worked out now.
    """

    def forward(self) -> None:
        self.database.execute('ALTER TABLE `info` ADD `origin` TEXT')
        self.database.execute('ALTER TABLE `info` ADD `origin_date` TEXT')

    def backward(self) -> None:
        self.database.execute('ALTER TABLE `info` DROP COLUMN `origin_date`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `origin`')
