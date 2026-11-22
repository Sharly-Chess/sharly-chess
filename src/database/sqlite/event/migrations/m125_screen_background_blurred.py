from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """An image screen can lay its own image, blurred, behind itself.

    The image then fills the screen instead of leaving bands around itself,
    so a screen set this way makes no use of its background colour.
    """

    def forward(self) -> None:
        self.database.execute(
            'ALTER TABLE `screen` ADD `background_blurred` INTEGER NOT NULL DEFAULT 0'
        )

    def backward(self) -> None:
        self.database.execute('ALTER TABLE `screen` DROP COLUMN `background_blurred`')
