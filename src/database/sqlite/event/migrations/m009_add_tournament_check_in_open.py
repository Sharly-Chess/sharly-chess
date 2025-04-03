from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `tournament` ADD `check_in_open` INTEGER NOT NULL DEFAULT 0'
        )
