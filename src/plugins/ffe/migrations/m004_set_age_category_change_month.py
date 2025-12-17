import json
from plugins.migration import BasePluginMigration


class Migration(BasePluginMigration):
    def forward(self):
        self.database.execute('SELECT `enabled_plugins` FROM `info`')
        enabled_plugins = json.loads(self.database.fetchone()['enabled_plugins'])
        if 'ffe' in enabled_plugins:
            self.database.execute('UPDATE `info` SET `age_category_change_month` = 9')

    def backward(self):
        pass
