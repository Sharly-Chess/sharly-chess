from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'CREATE TABLE `local_source_database` ('
            '   `name` TEXT NOT NULL,'
            '   `outdate_delay` TEXT NOT NULL,'
            '   `outdate_action` TEXT NOT NULL,'
            '   `updated_at` FLOAT,'
            '    PRIMARY KEY(`name`)'
            ')'
        )

    def backward(self):
        self.database.execute('DROP TABLE `local_source_database`')
