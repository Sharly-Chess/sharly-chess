from database.sqlite.migration import AbstractMigration


class Migration(AbstractMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `screen` ADD `results_max_age` INTEGER')
        self.database.execute(
            'ALTER TABLE `info` DROP COLUMN `allow_results_deletion_on_input_screens`'
        )
