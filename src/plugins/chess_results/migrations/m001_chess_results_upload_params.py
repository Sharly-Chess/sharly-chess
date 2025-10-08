from plugins.migration import BasePluginMigration


class Migration(BasePluginMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `info` ADD `chess_results_auto_upload` INTEGER NOT NULL DEFAULT 0'
        )
        self.database.execute(
            'ALTER TABLE `info` ADD `chess_results_auto_upload_delay` INTEGER'
        )

        self.database.execute(
            'ALTER TABLE `tournament` ADD `chess_results_trn` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `chess_results_creator_id` TEXT'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `chess_results_auto_upload` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `chess_results_last_upload` FLOAT NOT NULL DEFAULT 0.0'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `info` DROP COLUMN `chess_results_auto_upload`'
        )
        self.database.execute(
            'ALTER TABLE `info` DROP COLUMN `chess_results_auto_upload_delay`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `chess_results_auto_upload`'
        )
