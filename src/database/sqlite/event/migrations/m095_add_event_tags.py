from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Adds the tags of the event, stored as a JSON list of the ids of the
    tags defined in the config database."""

    def forward(self):
        self.database.execute(
            "ALTER TABLE `info` ADD `tag_ids` TEXT NOT NULL DEFAULT '[]'"
        )

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `tag_ids`')
