from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self) -> None:
        self.database.execute(
            'CREATE TABLE `plugin` ('
            '   `name` TEXT NOT NULL,'
            '   `is_enabled` INTEGER NOT NULL,'
            '    PRIMARY KEY(`name`)'
            ')'
        )

    def backward(self) -> None:
        self.database.execute('DROP TABLE `plugin`')
