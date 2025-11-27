import json

from database.sqlite.migration import BaseMigration, PostUpgradeTask


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            "ALTER TABLE `info` ADD `enabled_plugins` TEXT DEFAULT '[]'"
        )
        # Required for previous post-upgrade tasks (FFE import)
        self.database.execute(
            'UPDATE `info` SET `enabled_plugins` = ?',
            (json.dumps(['ffe', 'pairing_acceleration']),),
        )
        self.post_upgrade_tasks.append(PostUpgradeTask(self.set_enabled_plugins))

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `enabled_plugins`')

    def set_enabled_plugins(self):
        from database.sqlite.event.event_database import EventDatabase
        from plugins.manager import plugin_manager
        from plugins.utils import Plugin

        assert isinstance(self.database, EventDatabase)
        with EventDatabase(self.database.uniq_id, True) as database:
            stored_event = database.load_stored_event()
            event_plugins: list[Plugin] = []
            fra_required = False
            for plugin in plugin_manager.enabled_plugins:
                if any(
                    plugin.used_by_stored_tournament(stored_event, stored_tournament)
                    for stored_tournament in stored_event.stored_tournaments
                ):
                    if plugin.federation == 'FRA':
                        fra_required = True
                    event_plugins.append(plugin)
            event_plugins = plugin_manager.get_plugins_with_dependencies(event_plugins)
            database.execute(
                'UPDATE `info` SET `enabled_plugins` = ?',
                (json.dumps([plugin.id for plugin in event_plugins]),),
            )
            if fra_required:
                database.execute('UPDATE `info` SET `federation` = ?', ('FRA',))
