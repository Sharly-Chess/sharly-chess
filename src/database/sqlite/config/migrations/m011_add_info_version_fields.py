from common import SHARLY_CHESS_VERSION, DEVEL_ENV
from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `info` ADD `check_beta_versions` INTEGER NOT NULL DEFAULT 0'
        )
        self.database.execute('ALTER TABLE `info` ADD `last_notified_version` TEXT')
        if DEVEL_ENV or SHARLY_CHESS_VERSION.is_prerelease:
            self.database.execute('UPDATE `info` SET `check_beta_versions` = 1')

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `check_beta_versions`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `last_notified_version`')
