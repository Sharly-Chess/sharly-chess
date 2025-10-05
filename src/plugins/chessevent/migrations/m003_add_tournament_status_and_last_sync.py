from plugins.migration import BasePluginMigration


class Migration(BasePluginMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `tournament` ADD `chessevent_status` TEXT')
        self.database.execute(
            'ALTER TABLE `tournament` ADD `chessevent_last_sync` FLOAT'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `chessevent_last_sync`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `chessevent_status`'
        )
