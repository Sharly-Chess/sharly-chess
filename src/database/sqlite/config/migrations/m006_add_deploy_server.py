from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `info` ADD `deploy_server` INTEGER NOT NULL DEFAULT 0'
        )

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `deploy_server`')
