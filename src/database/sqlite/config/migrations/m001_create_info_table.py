from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'CREATE TABLE `info` ('
            '    `force_edit` INTEGER NOT NULL,'
            '    `log_level` INTEGER,'
            '    `launch_browser` INTEGER,'
            '    `federation` TEXT,'
            '    `locale` TEXT'
            ')'
        )
        self.database.execute('INSERT INTO `info`(`force_edit`) VALUES (?)', (True,))

    def backward(self):
        self.database.execute('DROP TABLE `info`')
