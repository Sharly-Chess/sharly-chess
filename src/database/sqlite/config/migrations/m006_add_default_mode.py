from data.auth.exec_mode import ExecMode
from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            f'ALTER TABLE `info` ADD `default_mode` INTEGER NOT NULL DEFAULT {ExecMode.STAND_ALONE.value}'
        )
        self.database.execute('UPDATE `info` SET `force_edit` = 1')

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `default_mode`')
