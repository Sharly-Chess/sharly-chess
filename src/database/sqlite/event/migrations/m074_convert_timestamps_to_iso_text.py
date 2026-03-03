import json
from datetime import datetime, timezone

from database.sqlite.migration import BaseMigration

_TIMESTAMP_TRIGGERS = [
    'set_tournament_last_pairing_update_on_pairing_insert',
    'set_tournament_last_pairing_update_on_pairing_update',
    'set_tournament_last_pairing_update_on_pairing_delete',
    'set_tournament_last_pairing_update_on_board_update',
    'set_tournament_last_player_update_on_player_update',
    'set_tournament_last_player_update_on_tournament_player_insert',
    'set_tournament_last_player_update_on_tournament_player_update',
    'set_tournament_last_player_update_on_tournament_player_delete',
]

_DIRTY_FLAG_TRIGGER = 'mark_tournament_dirty_on_relevant_update'

# ChessEventTournamentPluginData.last_sync
# ChessResultsTournamentPluginData.last_upload
# FfeTournamentPluginData.last_rules_upload/last_upload
_PLUGIN_TIMESTAMP_KEYS = [
    ('chess_results', 'last_upload'),
    ('chessevent', 'last_sync'),
    ('ffe', 'last_upload'),
    ('ffe', 'last_rules_upload'),
]


# Why +00:00 suffix is needed:
# - Explicit UTC indicator for self-documenting storage format
# - Ensures backward migration correctness: SQLite strftime('%s') treats text as UTC
# - Allows datetime.fromisoformat() to parse as UTC-aware datetime
class Migration(BaseMigration):
    def _drop_all_triggers(self):
        for trigger in _TIMESTAMP_TRIGGERS + [_DIRTY_FLAG_TRIGGER]:
            self.database.execute(f'DROP TRIGGER IF EXISTS `{trigger}`')

    def _convert_column_to_text(self, table: str, column: str, nullable: bool):
        """Rename FLOAT column → _old, add TEXT column, copy converted data, drop _old."""
        old = f'_{column}_old'
        self.database.execute(
            f'ALTER TABLE `{table}` RENAME COLUMN `{column}` TO `{old}`'
        )
        if nullable:
            self.database.execute(f'ALTER TABLE `{table}` ADD COLUMN `{column}` TEXT')
        else:
            self.database.execute(
                f"ALTER TABLE `{table}` ADD COLUMN `{column}` TEXT NOT NULL DEFAULT ''"
            )
        self.database.execute(
            f'UPDATE `{table}` SET `{column}` = '
            f"strftime('%Y-%m-%d %H:%M:%f', `{old}`, 'unixepoch') || '+00:00' "
            f'WHERE `{old}` IS NOT NULL AND `{old}` > 0'
        )
        self.database.execute(f'ALTER TABLE `{table}` DROP COLUMN `{old}`')

    def _convert_column_to_float(self, table: str, column: str, nullable: bool):
        """Rename TEXT column → _old, add FLOAT column, copy converted data, drop _old."""
        old = f'_{column}_old'
        self.database.execute(
            f'ALTER TABLE `{table}` RENAME COLUMN `{column}` TO `{old}`'
        )
        if nullable:
            self.database.execute(f'ALTER TABLE `{table}` ADD COLUMN `{column}` REAL')
        else:
            self.database.execute(
                f'ALTER TABLE `{table}` ADD COLUMN `{column}` REAL NOT NULL DEFAULT 0'
            )
        self.database.execute(
            f'UPDATE `{table}` SET `{column}` = '
            f"CAST(strftime('%s', replace(`{old}`, '+00:00', '')) AS REAL) "
            f"+ (CAST(strftime('%f', replace(`{old}`, '+00:00', '')) AS REAL) "
            f"- CAST(strftime('%S', replace(`{old}`, '+00:00', '')) AS REAL)) "
            f"WHERE `{old}` IS NOT NULL AND `{old}` != ''"
        )
        self.database.execute(f'ALTER TABLE `{table}` DROP COLUMN `{old}`')

    def _recreate_timestamp_triggers_iso(self):
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_pairing_update_on_pairing_insert`
            AFTER INSERT ON `pairing`
            BEGIN
                UPDATE `tournament`
                SET `last_pairing_update` = strftime('%Y-%m-%d %H:%M:%f', 'now') || '+00:00'
                WHERE `id` = `NEW`.`tournament_id`;
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_pairing_update_on_pairing_update`
            AFTER UPDATE ON `pairing`
            BEGIN
                UPDATE `tournament`
                SET `last_pairing_update` = strftime('%Y-%m-%d %H:%M:%f', 'now') || '+00:00'
                WHERE `id` = `NEW`.`tournament_id`;
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_pairing_update_on_pairing_delete`
            AFTER DELETE ON `pairing`
            BEGIN
                UPDATE `tournament`
                SET `last_pairing_update` = strftime('%Y-%m-%d %H:%M:%f', 'now') || '+00:00'
                WHERE `id` = `OLD`.`tournament_id`;
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_pairing_update_on_board_update`
            AFTER UPDATE ON `board`
            BEGIN
                UPDATE `tournament`
                SET `last_pairing_update` = strftime('%Y-%m-%d %H:%M:%f', 'now') || '+00:00'
                WHERE `id` = (
                    SELECT `tournament_id` FROM `pairing`
                    WHERE `board_id` = `NEW`.`id`
                    LIMIT 1
                );
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_player_update_on_player_update`
            AFTER UPDATE ON `player`
            BEGIN
                UPDATE `tournament`
                SET `last_player_update` = strftime('%Y-%m-%d %H:%M:%f', 'now') || '+00:00'
                WHERE `id` IN (
                    SELECT `tournament_id` FROM `tournament_player`
                    WHERE `player_id` = `NEW`.`id`
                );
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_player_update_on_tournament_player_insert`
            AFTER INSERT ON `tournament_player`
            BEGIN
                UPDATE `tournament`
                SET `last_player_update` = strftime('%Y-%m-%d %H:%M:%f', 'now') || '+00:00'
                WHERE `id` = `NEW`.`tournament_id`;
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_player_update_on_tournament_player_update`
            AFTER UPDATE ON `tournament_player`
            BEGIN
                UPDATE `tournament`
                SET `last_player_update` = strftime('%Y-%m-%d %H:%M:%f', 'now') || '+00:00'
                WHERE `id` = `NEW`.`tournament_id`;
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_player_update_on_tournament_player_delete`
            AFTER DELETE ON `tournament_player`
            BEGIN
                UPDATE `tournament`
                SET `last_player_update` = strftime('%Y-%m-%d %H:%M:%f', 'now') || '+00:00'
                WHERE `id` = `OLD`.`tournament_id`;
            END;
            """
        )

    def _recreate_timestamp_triggers_float(self):
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_pairing_update_on_pairing_insert`
            AFTER INSERT ON `pairing`
            BEGIN
                UPDATE `tournament` SET `last_pairing_update` = unixepoch('subsec')
                WHERE `id` = `NEW`.`tournament_id`;
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_pairing_update_on_pairing_update`
            AFTER UPDATE ON `pairing`
            BEGIN
                UPDATE `tournament` SET `last_pairing_update` = unixepoch('subsec')
                WHERE `id` = `NEW`.`tournament_id`;
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_pairing_update_on_pairing_delete`
            AFTER DELETE ON `pairing`
            BEGIN
                UPDATE `tournament` SET `last_pairing_update` = unixepoch('subsec')
                WHERE `id` = `OLD`.`tournament_id`;
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_pairing_update_on_board_update`
            AFTER UPDATE ON `board`
            BEGIN
                UPDATE `tournament` SET `last_pairing_update` = unixepoch('subsec')
                WHERE `id` = (
                    SELECT `tournament_id` FROM `pairing`
                    WHERE `board_id` = `NEW`.`id`
                    LIMIT 1
                );
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_player_update_on_player_update`
            AFTER UPDATE ON `player`
            BEGIN
                UPDATE `tournament` SET `last_player_update` = unixepoch('subsec')
                WHERE `id` IN (
                    SELECT `tournament_id` FROM `tournament_player`
                    WHERE `player_id` = `NEW`.`id`
                );
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_player_update_on_tournament_player_insert`
            AFTER INSERT ON `tournament_player`
            BEGIN
                UPDATE `tournament` SET `last_player_update` = unixepoch('subsec')
                WHERE `id` = `NEW`.`tournament_id`;
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_player_update_on_tournament_player_update`
            AFTER UPDATE ON `tournament_player`
            BEGIN
                UPDATE `tournament` SET `last_player_update` = unixepoch('subsec')
                WHERE `id` = `NEW`.`tournament_id`;
            END;
            """
        )
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `set_tournament_last_player_update_on_tournament_player_delete`
            AFTER DELETE ON `tournament_player`
            BEGIN
                UPDATE `tournament` SET `last_player_update` = unixepoch('subsec')
                WHERE `id` = `OLD`.`tournament_id`;
            END;
            """
        )

    def _recreate_dirty_flag_trigger(self):
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `mark_tournament_dirty_on_relevant_update`
            AFTER UPDATE OF `last_pairing_update`, `last_player_update`, `last_update` ON `tournament`
            WHEN (NEW.`last_pairing_update` IS NOT OLD.`last_pairing_update`)
              OR (NEW.`last_player_update`  IS NOT OLD.`last_player_update`)
              OR (NEW.`last_update`         IS NOT OLD.`last_update`)
            BEGIN
                UPDATE `tournament`
                    SET `dirty` = 1
                    WHERE `id` = NEW.`id`;
            END;
            """
        )

    def _convert_timer_hour_triggered_at_to_iso(self):
        """Convert timer_hour.triggered_at from local %Y-%m-%dT%H:%M TEXT to UTC ISO TEXT."""
        self.database.execute('SELECT `id`, `triggered_at` FROM `timer_hour`')
        rows = list(self.database.fetchall())
        for row in rows:
            value = row['triggered_at']
            if not value:
                continue
            try:
                local_dt = datetime.strptime(value, '%Y-%m-%dT%H:%M')
                iso = local_dt.astimezone(timezone.utc).isoformat(
                    sep=' ', timespec='milliseconds'
                )
                self.database.execute(
                    'UPDATE `timer_hour` SET `triggered_at` = ? WHERE `id` = ?',
                    (iso, row['id']),
                )
            except ValueError:
                pass

    def _convert_timer_hour_triggered_at_to_local_text(self):
        """Convert timer_hour.triggered_at from UTC ISO TEXT back to local %Y-%m-%dT%H:%M TEXT."""
        self.database.execute('SELECT `id`, `triggered_at` FROM `timer_hour`')
        rows = list(self.database.fetchall())
        for row in rows:
            value = row['triggered_at']
            if not value:
                continue
            try:
                local_dt = (
                    datetime.fromisoformat(value).astimezone().replace(tzinfo=None)
                )
                self.database.execute(
                    'UPDATE `timer_hour` SET `triggered_at` = ? WHERE `id` = ?',
                    (local_dt.strftime('%Y-%m-%dT%H:%M'), row['id']),
                )
            except ValueError:
                pass

    def _convert_plugin_timestamps_to_iso(self):
        """Convert epoch floats to UTC ISO TEXT in plugin_data JSON timestamps."""
        self.database.execute('SELECT `id`, `plugin_data` FROM `tournament`')
        rows = self.database.fetchall()
        for row in rows:
            tournament_id = row['id']
            plugin_data = json.loads(row['plugin_data']) if row['plugin_data'] else {}
            changed = False
            for plugin_key, ts_key in _PLUGIN_TIMESTAMP_KEYS:
                plugin = plugin_data.get(plugin_key)
                if not isinstance(plugin, dict):
                    continue
                value = plugin.get(ts_key)
                if isinstance(value, (int, float)) and value > 0:
                    plugin[ts_key] = datetime.fromtimestamp(
                        value, tz=timezone.utc
                    ).isoformat(sep=' ', timespec='milliseconds')
                    changed = True
            if changed:
                self.database.execute(
                    'UPDATE `tournament` SET `plugin_data` = ? WHERE `id` = ?',
                    (json.dumps(plugin_data), tournament_id),
                )

    def _convert_plugin_timestamps_to_float(self):
        """Convert UTC ISO TEXT back to epoch floats in plugin_data JSON timestamps."""
        self.database.execute('SELECT `id`, `plugin_data` FROM `tournament`')
        rows = self.database.fetchall()
        for row in rows:
            tournament_id = row['id']
            plugin_data = json.loads(row['plugin_data']) if row['plugin_data'] else {}
            changed = False
            for plugin_key, ts_key in _PLUGIN_TIMESTAMP_KEYS:
                plugin = plugin_data.get(plugin_key)
                if not isinstance(plugin, dict):
                    continue
                value = plugin.get(ts_key)
                if isinstance(value, str) and value:
                    try:
                        plugin[ts_key] = datetime.fromisoformat(value).timestamp()
                        changed = True
                    except ValueError:
                        pass
            if changed:
                self.database.execute(
                    'UPDATE `tournament` SET `plugin_data` = ? WHERE `id` = ?',
                    (json.dumps(plugin_data), tournament_id),
                )

    def forward(self):
        # Drop all triggers (required before renaming columns they reference)
        self._drop_all_triggers()

        # Convert FLOAT columns to TEXT
        self._convert_column_to_text('tournament', 'last_update', nullable=False)
        self._convert_column_to_text('tournament', 'last_player_update', nullable=False)
        self._convert_column_to_text(
            'tournament', 'last_pairing_update', nullable=False
        )
        self._convert_column_to_text('board', 'last_result_update', nullable=True)
        self._convert_column_to_text('screen', 'last_update', nullable=False)
        self._convert_column_to_text('screen_set', 'last_update', nullable=False)
        self._convert_column_to_text('family', 'last_update', nullable=False)
        self._convert_column_to_text('display_controller', 'last_update', nullable=True)

        # Convert timer_hour.triggered_at from local TEXT to UTC ISO TEXT
        self._convert_timer_hour_triggered_at_to_iso()

        # Convert plugin_data JSON timestamps
        self._convert_plugin_timestamps_to_iso()

        # Recreate triggers with ISO format
        self._recreate_timestamp_triggers_iso()
        self._recreate_dirty_flag_trigger()

    def backward(self):
        # Drop all triggers
        self._drop_all_triggers()

        # Convert TEXT columns back to FLOAT
        self._convert_column_to_float('tournament', 'last_update', nullable=False)
        self._convert_column_to_float(
            'tournament', 'last_player_update', nullable=False
        )
        self._convert_column_to_float(
            'tournament', 'last_pairing_update', nullable=False
        )
        self._convert_column_to_float('board', 'last_result_update', nullable=True)
        self._convert_column_to_float('screen', 'last_update', nullable=False)
        self._convert_column_to_float('screen_set', 'last_update', nullable=False)
        self._convert_column_to_float('family', 'last_update', nullable=False)
        self._convert_column_to_float(
            'display_controller', 'last_update', nullable=True
        )

        # Convert timer_hour.triggered_at from UTC ISO TEXT back to local TEXT
        self._convert_timer_hour_triggered_at_to_local_text()

        # Convert plugin_data JSON timestamps back to float
        self._convert_plugin_timestamps_to_float()

        # Recreate triggers with unixepoch('subsec')
        self._recreate_timestamp_triggers_float()
        self._recreate_dirty_flag_trigger()
