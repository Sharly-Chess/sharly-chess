import json
from plugins.migration import BasePluginMigration


class Migration(BasePluginMigration):
    def forward(self):
        # Event data
        self.database.execute(
            'SELECT plugin_data, ffe_auto_upload, ffe_auto_upload_delay FROM info'
        )
        info = self.database.fetchone()

        try:
            plugin_data = json.loads(info['plugin_data'] or '{}')
        except Exception:
            plugin_data = {}

        plugin_data['ffe'] = {
            'auto_upload_delay': info['ffe_auto_upload_delay'],
            'auto_upload': info['ffe_auto_upload'],
        }

        self.database.execute(
            'UPDATE info SET plugin_data = ?',
            (json.dumps(plugin_data),),
        )

        self.database.execute('ALTER TABLE `info` DROP COLUMN `ffe_auto_upload`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `ffe_auto_upload_delay`')

        # Tournament data
        self.database.execute(
            'SELECT id, plugin_data, ffe_id, ffe_password, '
            'ffe_last_upload, ffe_last_rules_upload, ffe_auto_upload '
            'FROM tournament'
        )

        for row in self.database.fetchall():
            tournament_id = row['id']
            try:
                plugin_data = json.loads(row['plugin_data'] or '{}')
            except Exception:
                plugin_data = {}

            plugin_data['ffe'] = {
                'ffe_id': row['ffe_id'],
                'password': row['ffe_password'],
                'last_upload': row['ffe_last_upload'],
                'last_rules_upload': row['ffe_last_rules_upload'],
                'auto_upload': row['ffe_auto_upload'],
            }

            self.database.execute(
                'UPDATE tournament SET plugin_data = ? WHERE id = ?',
                (json.dumps(plugin_data), tournament_id),
            )

        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `ffe_id`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `ffe_password`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `ffe_auto_upload`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `ffe_last_upload`')
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `ffe_last_rules_upload`'
        )

    def backward(self):
        # Event data

        self.database.execute(
            'ALTER TABLE `info` ADD `ffe_auto_upload` INTEGER NOT NULL DEFAULT 0'
        )
        self.database.execute('ALTER TABLE `info` ADD `ffe_auto_upload_delay` INTEGER')

        self.database.execute('SELECT plugin_data FROM info')
        info = self.database.fetchone()
        try:
            plugin_data = json.loads(info['plugin_data'] or '{}')
        except Exception:
            plugin_data = {}

        ffe_data = plugin_data.get('ffe', {}) or {}

        self.database.execute(
            """
            UPDATE info
            SET ffe_auto_upload = ?,
                ffe_auto_upload_delay = ?
            """,
            (
                ffe_data.get('auto_upload', None),
                ffe_data.get('auto_upload_delay', None),
            ),
        )

        # Tournament data
        self.database.execute('ALTER TABLE `tournament` ADD `ffe_id` INTEGER')
        self.database.execute('ALTER TABLE `tournament` ADD `ffe_password` TEXT')
        self.database.execute(
            'ALTER TABLE `tournament` ADD `ffe_last_upload` FLOAT NOT NULL DEFAULT 0.0'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `ffe_last_rules_upload` FLOAT NOT NULL DEFAULT 0.0'
        )
        self.database.execute('ALTER TABLE `tournament` ADD `ffe_auto_upload` INTEGER')

        self.database.execute('SELECT id, plugin_data FROM tournament')
        for row in self.database.fetchall():
            tournament_id = row['id']
            try:
                plugin_data = json.loads(row['plugin_data'] or '{}')
            except Exception:
                plugin_data = {}

            ffe_data = plugin_data.get('ffe', {}) or {}

            self.database.execute(
                """
                UPDATE tournament
                SET ffe_id = ?,
                    ffe_password = ?,
                    ffe_last_upload = ?,
                    ffe_last_rules_upload = ?,
                    ffe_auto_upload = ?
                WHERE id = ?
                """,
                (
                    ffe_data.get('id', None),
                    ffe_data.get('password', None),
                    ffe_data.get('last_upload', None),
                    ffe_data.get('last_rules_upload', None),
                    ffe_data.get('auto_upload', None),
                    tournament_id,
                ),
            )
