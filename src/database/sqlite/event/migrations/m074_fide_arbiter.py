from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            "ALTER TABLE `player` ADD COLUMN `arbiter_title` TEXT NOT NULL DEFAULT ''"
        )

    def backward(self):
        self.database.execute('ALTER TABLE `player` DROP COLUMN `arbiter_title`')
