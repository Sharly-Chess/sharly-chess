from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'CREATE TABLE `plugin` ('
            '   `name` TEXT NOT NULL,'
            '   `is_enabled` INTEGER NOT NULL,'
            '    PRIMARY KEY(`name`)'
            ')'
        )

    def backward(self):
        self.database.execute('DROP TABLE `plugin`')
