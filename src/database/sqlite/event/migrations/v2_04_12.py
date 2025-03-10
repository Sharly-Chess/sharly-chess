from database.sqlite.migration import AbstractMigration


class Migration(AbstractMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `info` ADD `rules` TEXT')
        self.database.execute('ALTER TABLE `tournament` ADD `rules` TEXT')
