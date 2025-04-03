from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `tournament` ADD `last_ffe_rules_upload` FLOAT'
        )
        self.database.execute('UPDATE `tournament` SET `last_ffe_rules_upload` = 0.0')
