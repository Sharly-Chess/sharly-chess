from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self) -> None:
        self.database.execute('ALTER TABLE `info` ADD `rules` TEXT')
        self.database.execute('ALTER TABLE `tournament` ADD `rules` TEXT')
