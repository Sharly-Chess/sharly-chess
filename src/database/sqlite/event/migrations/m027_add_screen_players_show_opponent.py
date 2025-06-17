from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `screen` ADD `players_show_opponent` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `family` ADD `players_show_opponent` INTEGER'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `family` DROP COLUMN `players_show_opponent`'
        )
        self.database.execute(
            'ALTER TABLE `screen` DROP COLUMN `players_show_opponent`'
        )
