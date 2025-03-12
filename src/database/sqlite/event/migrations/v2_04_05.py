from database.sqlite.migration import AbstractMigration


class Migration(AbstractMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `rotator` DROP COLUMN `show_menus`')
