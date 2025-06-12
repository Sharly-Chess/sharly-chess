from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `info` ADD `deploy_server` INTEGER')
        self.database.execute('UPDATE `info` SET `deploy_server` = NOT `force_edit`')

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `deploy_server`')
