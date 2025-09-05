from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('SELECT `federation` FROM `info`')
        if not self.database.fetchone()['federation']:
            self.database.execute('UPDATE `info` SET `force_edit` = 1')

    def backward(self):
        pass
