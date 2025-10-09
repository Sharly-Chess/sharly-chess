import json
from plugins.migration import BasePluginMigration


class Migration(BasePluginMigration):
    def forward(self):
        # Event data
        self.database.execute(
            'SELECT plugin_data, chessevent_user_id, chessevent_password, chessevent_event_id FROM info'
        )
        info = self.database.fetchone()

        try:
            plugin_data = json.loads(info['plugin_data'] or '{}')
        except Exception:
            plugin_data = {}

        plugin_data['chessevent'] = {
            'user': info['chessevent_user_id'],
            'password': info['chessevent_password'],
            'event_id': info['chessevent_event_id'],
        }

        self.database.execute(
            'UPDATE info SET plugin_data = ?',
            (json.dumps(plugin_data),),
        )

        self.database.execute('ALTER TABLE `info` DROP COLUMN `chessevent_user_id`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `chessevent_password`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `chessevent_event_id`')

        # Tournament data
        self.database.execute(
            'SELECT id, chessevent_user_id, chessevent_password, chessevent_event_id, '
            'chessevent_tournament_name, chessevent_status, chessevent_last_sync '
            'FROM tournament'
        )

        for row in self.database.fetchall():
            tournament_id = row['id']
            try:
                plugin_data = json.loads(row['plugin_data'] or '{}')
            except Exception:
                plugin_data = {}

            plugin_data['chessevent'] = {
                'user': row['chessevent_user_id'],
                'password': row['chessevent_password'],
                'event_id': row['chessevent_event_id'],
                'tournament_name': row['chessevent_tournament_name'],
                'status': row['chessevent_status'],
                'last_sync': row['chessevent_last_sync'],
            }

            self.database.execute(
                'UPDATE tournament SET plugin_data = ? WHERE id = ?',
                (json.dumps(plugin_data), tournament_id),
            )

        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `chessevent_user_id`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `chessevent_password`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `chessevent_event_id`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `chessevent_tournament_name`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `chessevent_status`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `chessevent_last_sync`'
        )

    def backward(self):
        # Event data

        self.database.execute('ALTER TABLE `info` ADD `chessevent_user_id` TEXT')
        self.database.execute('ALTER TABLE `info` ADD `chessevent_password` TEXT')
        self.database.execute('ALTER TABLE `info` ADD `chessevent_event_id` TEXT')

        self.database.execute('SELECT plugin_data FROM info')
        info = self.database.fetchone()
        try:
            plugin_data = json.loads(info['plugin_data'] or '{}')
        except Exception:
            plugin_data = {}

        chessevent_data = plugin_data.get('chessevent', {}) or {}

        self.database.execute(
            """
            UPDATE info
            SET chessevent_user_id = ?,
                chessevent_password = ?,
                chessevent_event_id = ?
            WHERE id = ?
            """,
            (
                chessevent_data.get('user'),
                chessevent_data.get('password'),
                chessevent_data.get('event_id'),
            ),
        )

        # Tournament data
        self.database.execute('ALTER TABLE `tournament` ADD `chessevent_user_id` TEXT')
        self.database.execute('ALTER TABLE `tournament` ADD `chessevent_password` TEXT')
        self.database.execute('ALTER TABLE `tournament` ADD `chessevent_event_id` TEXT')
        self.database.execute(
            'ALTER TABLE `tournament` ADD `chessevent_tournament_name` TEXT'
        )
        self.database.execute('ALTER TABLE `tournament` ADD `chessevent_status` TEXT')
        self.database.execute(
            'ALTER TABLE `tournament` ADD `chessevent_last_sync` FLOAT'
        )

        self.database.execute('SELECT id, plugin_data FROM tournament')
        for row in self.database.fetchall():
            tournament_id = row['id']
            try:
                plugin_data = json.loads(row['plugin_data'] or '{}')
            except Exception:
                plugin_data = {}

            chessevent_data = plugin_data.get('chessevent', {}) or {}

            self.database.execute(
                """
                UPDATE tournament
                SET chessevent_user_id = ?,
                    chessevent_password = ?,
                    chessevent_event_id = ?,
                    chessevent_tournament_name = ?,
                    chessevent_status = ?,
                    chessevent_last_sync = ?
                WHERE id = ?
                """,
                (
                    chessevent_data.get('user'),
                    chessevent_data.get('password'),
                    chessevent_data.get('event_id'),
                    chessevent_data.get('tournament_name'),
                    chessevent_data.get('last_sync'),
                    tournament_id,
                ),
            )
