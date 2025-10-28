import json
from plugins.migration import BasePluginMigration


class Migration(BasePluginMigration):
    def forward(self):
        plugin_used = False
        self.database.execute('SELECT `plugin_data` from `tournament`')
        for row in self.database.fetchall():
            plugin_data = json.loads(row['plugin_data'])
            ce_data = plugin_data.get('chessevent', {})
            if ce_data.get('tournament_name', None):
                plugin_used = True
                break
        if not plugin_used:
            return
        self.database.execute('SELECT `enabled_plugins` FROM `info`')
        enabled_plugins: list[str] = json.loads(
            self.database.fetchone()['enabled_plugins']
        )
        if 'chessevent' in enabled_plugins:
            return
        enabled_plugins.append('chessevent')
        self.database.execute(
            'UPDATE `info` SET `enabled_plugins` = ?',
            (json.dumps(enabled_plugins),),
        )

    def backward(self):
        pass
