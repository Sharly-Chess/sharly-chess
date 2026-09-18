from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self) -> None:
        self.database.execute(
            'CREATE TABLE `player_category_set` ('
            '   `id` INTEGER NOT NULL,'
            '   `name` TEXT NOT NULL,'
            '   `categories` TEXT NOT NULL,'
            '    PRIMARY KEY(`id` AUTOINCREMENT)'
            ')'
        )

    def backward(self) -> None:
        self.database.execute('DROP TABLE `player_category_set`')
