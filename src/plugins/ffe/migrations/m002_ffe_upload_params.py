from plugins.migration import BasePluginMigration


class Migration(BasePluginMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `info` ADD `ffe_auto_upload` INTEGER NOT NULL DEFAULT 0'
        )
        self.database.execute('ALTER TABLE `info` ADD `ffe_auto_upload_delay` INTEGER')
        self.database.execute('ALTER TABLE `tournament` ADD `ffe_auto_upload` INTEGER')

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `ffe_auto_upload`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `ffe_auto_upload_delay`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `ffe_auto_upload`')
