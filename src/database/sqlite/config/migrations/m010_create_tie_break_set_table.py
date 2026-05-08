from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'CREATE TABLE `tie_break_set` ('
            '   `id` INTEGER NOT NULL,'
            '   `name` TEXT NOT NULL,'
            '   `pairing_system_id` TEXT NOT NULL,'
            '   `stored_tie_breaks` TEXT NOT NULL,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    UNIQUE(`pairing_system_id`, `name`)'
            ')'
        )

    def backward(self):
        self.database.execute('DROP TABLE `tie_break_set`')
