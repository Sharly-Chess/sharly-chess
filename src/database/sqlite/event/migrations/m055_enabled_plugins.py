import json

from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `info` ADD `enabled_plugins` TEXT')
        enabled_plugins = ['pairing_acceleration', 'ffe']
        self.database.execute(
            'UPDATE `info` SET `enabled_plugins` = ?',
            (json.dumps(enabled_plugins),),
        )

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `enabled_plugins`')
