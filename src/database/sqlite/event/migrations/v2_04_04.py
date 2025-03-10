from database.sqlite.migration import AbstractMigration


class Migration(AbstractMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `screen` ADD `input_exit_button` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `family` ADD `input_exit_button` INTEGER'
        )
