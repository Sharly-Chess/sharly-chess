import json
from database.sqlite.migration import BaseMigration, PostUpgradeTask


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'SELECT id, plugin_data, time_control_handicap_penalty_step, time_control_handicap_penalty_value, time_control_handicap_min_time '
            'FROM tournament'
        )
        for row in self.database.fetchall():
            tournament_id = row['id']
            plugin_data = json.loads(row['plugin_data'] or '{}')

            plugin_data['handicap_games'] = {
                'penalty_step': row['time_control_handicap_penalty_step'],
                'penalty_value': row['time_control_handicap_penalty_value'],
                'min_time': row['time_control_handicap_min_time'],
            }

            self.database.execute(
                'UPDATE tournament SET plugin_data = ? WHERE id = ?',
                (json.dumps(plugin_data), tournament_id),
            )

        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `time_control_handicap_penalty_step`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `time_control_handicap_penalty_value`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `time_control_handicap_min_time`'
        )
        self.post_upgrade_tasks.append(PostUpgradeTask(self.set_enabled_plugins))

    def backward(self):
        # Event data

        self.database.execute(
            'ALTER TABLE `tournament` ADD `time_control_handicap_penalty_step` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `time_control_handicap_penalty_value` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `time_control_handicap_min_time` INTEGER'
        )

        self.database.execute('SELECT id, plugin_data FROM tournament')
        for row in self.database.fetchall():
            tournament_id = row['id']
            plugin_data = json.loads(row['plugin_data'] or '{}')

            handicap_games_data = plugin_data.get('handicap_games', {}) or {}

            self.database.execute(
                """
                UPDATE tournament
                SET time_control_handicap_penalty_step = ?,
                    time_control_handicap_penalty_value = ?,
                    time_control_handicap_min_time = ?
                WHERE id = ?
                """,
                (
                    handicap_games_data.get('penalty_step', None),
                    handicap_games_data.get('penalty_value', None),
                    handicap_games_data.get('min_time', None),
                    tournament_id,
                ),
            )

    def set_enabled_plugins(self):
        from database.sqlite.event.event_database import EventDatabase
        from plugins.manager import plugin_manager
        from plugins.handicap_games.handicap_games import HandicapGamesPlugin

        assert isinstance(self.database, EventDatabase)
        with EventDatabase(self.database.uniq_id, True) as database:
            stored_event = database.load_stored_event()
            event_plugins: list[str] = stored_event.enabled_plugins
            handicap_games_plugin = plugin_manager.get_plugin_by_class(
                HandicapGamesPlugin
            )
            if any(
                handicap_games_plugin.used_by_stored_tournament(
                    stored_event, stored_tournament
                )
                for stored_tournament in stored_event.stored_tournaments
            ):
                event_plugins.append(handicap_games_plugin.id)
            database.execute(
                'UPDATE `info` SET `enabled_plugins` = ?',
                (json.dumps(event_plugins),),
            )
