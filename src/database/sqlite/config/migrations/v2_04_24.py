from database.sqlite.migration import AbstractMigration


class Migration(AbstractMigration):
    def forward(self):
        self.database.execute(
            'CREATE TABLE `info` ('
            '    `version` TEXT NOT NULL,'
            '    `force_edit` INTEGER NOT NULL,'
            '    `log_level` INTEGER,'
            '    `launch_browser` INTEGER,'
            '    `federation` TEXT,'
            '    `locale` TEXT'
            ')'
        )

    def backward(self):
        self.database.execute('DROP TABLE `info`')
