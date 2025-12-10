from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'CREATE TABLE `player_category_set` ('
            '   `id` INTEGER NOT NULL,'
            '   `name` TEXT NOT NULL,'
            '   `categories` TEXT NOT NULL,'
            '    PRIMARY KEY(`id` AUTOINCREMENT)'
            ')'
        )

    def backward(self):
        self.database.execute('DROP TABLE `player_category_set`')
