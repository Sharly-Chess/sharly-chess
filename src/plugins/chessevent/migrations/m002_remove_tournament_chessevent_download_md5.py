from plugins.migration import BasePluginMigration


class Migration(BasePluginMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `chessevent_last_download_md5`'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `tournament` ADD `chessevent_last_download_md5` TEXT'
        )
