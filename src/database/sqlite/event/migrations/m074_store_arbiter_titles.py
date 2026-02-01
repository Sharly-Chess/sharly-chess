from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `account` RENAME COLUMN `fide_arbiter_title` TO `arbiter_title`'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `account` RENAME COLUMN `arbiter_title` TO `fide_arbiter_title`'
        )
