from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Gives the computer a key pair of its own.

    The pair belongs to the computer rather than to any event: services it
    connects to recognise the computer by it, and tell it apart from a copy of
    its events running elsewhere. The columns hold nothing until the pair is
    first needed.
    """

    def forward(self) -> None:
        self.database.execute('ALTER TABLE `info` ADD `computer_private_key` TEXT')
        self.database.execute('ALTER TABLE `info` ADD `computer_public_key` TEXT')

    def backward(self) -> None:
        self.database.execute('ALTER TABLE `info` DROP COLUMN `computer_public_key`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `computer_private_key`')
