from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            "ALTER TABLE `player` ADD COLUMN `arbiter_title` TEXT NOT NULL DEFAULT ''"
        )
        self.database.execute(
            'ALTER TABLE `account` RENAME COLUMN `fide_arbiter_title` TO `arbiter_title`'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `account` RENAME COLUMN `arbiter_title` TO `fide_arbiter_title`'
        )
        self.database.execute('ALTER TABLE `player` DROP COLUMN `arbiter_title`')
