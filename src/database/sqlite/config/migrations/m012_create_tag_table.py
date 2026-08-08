from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Creates the table holding the event tags.

    Tags are global to the installation: every event references them by id
    through its own `info`.`tags` column, so renaming an event (or its
    database file) never loses its tags."""

    def forward(self):
        self.database.execute(
            'CREATE TABLE `tag` ('
            '   `id` INTEGER NOT NULL,'
            '   `name` TEXT NOT NULL,'
            '   `color` TEXT NOT NULL,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    UNIQUE(`name`)'
            ')'
        )

    def backward(self):
        self.database.execute('DROP TABLE `tag`')
