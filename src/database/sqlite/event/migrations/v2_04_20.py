from database.sqlite.migration import AbstractMigration


class Migration(AbstractMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `tournament` ADD `check_in_open` INTEGER NOT NULL DEFAULT 0'
        )
