from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `screen` ADD `input_exit_button` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `family` ADD `input_exit_button` INTEGER'
        )
