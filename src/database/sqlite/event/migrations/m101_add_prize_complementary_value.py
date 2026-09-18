from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self) -> None:
        self.database.execute('ALTER TABLE `prize` ADD `complementary_value` REAL')

    def backward(self) -> None:
        self.database.execute('ALTER TABLE `prize` DROP COLUMN `complementary_value`')
