from typing import Any

from database.sqlite.migration import AbstractMigration


class Migration(AbstractMigration):
    def forward(self):
        # No need to store the rounds skipped by the users since pairing information is stored
        # at player-level after the ChessEvent import. IF EXISTS is used because the table is not
        # created since 2.4.20
        self.database.execute('DROP TABLE IF EXISTS `skipped_round`')
        self.database.execute(
            "ALTER TABLE `info` ADD `federation` TEXT NOT NULL DEFAULT 'NON'"
        )
        # Assume that the events before 2.4.21 were all in France
        self.database.execute('UPDATE `info` SET `federation` = ?', ('FRA',))
        # Add ChessEvent information at event-level and tournament-level
        self.database.execute('ALTER TABLE `info` ADD `chessevent_user_id` TEXT')
        self.database.execute('ALTER TABLE `info` ADD `chessevent_password` TEXT')
        self.database.execute('ALTER TABLE `info` ADD `chessevent_event_id` TEXT')
        self.database.execute(
            'ALTER TABLE `tournament` ADD `chessevent_user_id` TEXT'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `chessevent_password` TEXT'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `chessevent_event_id` TEXT'
        )
        # Read all the ChessEvent connections
        self.database.execute('SELECT * FROM `chessevent` ORDER BY `id`')
        chessevent_connections: dict[int, dict[str, Any]] = {
            row['id']: {
                'chessevent_user_id': row['user_id'],
                'chessevent_password': row['password'],
                'chessevent_event_id': row['event_id'],
            }
            for row in self.database._fetchall()
        }
        if len(chessevent_connections) == 1:
            # Set the ChessEvent connection as the event default ChessEvent connection
            event_chessevent_connection: dict[str, Any] = list(
                chessevent_connections.values()
            )[0]
            self.database.execute(
                f'UPDATE `info` SET {", ".join(f"`{field}` = ?" for field in event_chessevent_connection)}',
                tuple(event_chessevent_connection.values()),
            )
        else:
            # Read the tournaments and set the ChessEvent information of the tournament
            self.database.execute(
                'SELECT `id`, `chessevent_id` FROM `tournament` WHERE `chessevent_id` IS NOT NULL'
            )
            for row in self.database._fetchall():
                chessevent_connection: dict[str, Any] = (
                    chessevent_connections[row['chessevent_id']]
                )
                self.database.execute(
                    f'UPDATE `tournament` SET {", ".join(f"`{field}` = ?" for field in chessevent_connection)} WHERE `id` = ?',
                    tuple(
                        list(chessevent_connection.values()) + [row['id']]
                    ),
                )
        # Simply running ALTER TABLE `tournament` DROP COLUMN `chessevent_id` fails with sqlite3.OperationalError:
        # error in table tournament after drop column: unknown column "chessevent_id" in foreign key definition
        # Since there is no simple way in SQlite to remove a constraint (https://sqlite.org/lang_altertable.html part 7),
        # copy the table and rename:
        self.database.execute('PRAGMA foreign_keys=off')
        self.database.execute(
            'ALTER TABLE `tournament` RENAME TO `tournament_copy`'
        )
        self.database.execute(
            'CREATE TABLE `tournament` ('
            '    `id` INTEGER NOT NULL,'
            '    `uniq_id` TEXT NOT NULL,'
            '    `name` TEXT NOT NULL,'
            '    `path` TEXT,'
            '    `filename` TEXT,'
            '    `ffe_id` INTEGER,'
            '    `ffe_password` TEXT,'
            '    `time_control_initial_time` INTEGER,'
            '    `time_control_increment` INTEGER,'
            '    `time_control_handicap_penalty_step` INTEGER,'
            '    `time_control_handicap_penalty_value` INTEGER,'
            '    `time_control_handicap_min_time` INTEGER,'
            '    `chessevent_user_id` TEXT,'
            '    `chessevent_password` TEXT,'
            '    `chessevent_event_id` TEXT,'
            '    `chessevent_tournament_name` TEXT,'
            '    `record_illegal_moves` INTEGER,'
            '    `rules` TEXT,'
            '    `check_in_open` INTEGER NOT NULL DEFAULT 0,'
            '    `last_update` FLOAT NOT NULL,'
            '    `last_illegal_move_update` FLOAT NOT NULL DEFAULT 0.0,'
            '    `last_result_update` FLOAT NOT NULL DEFAULT 0.0,'
            '    `last_check_in_update` FLOAT NOT NULL DEFAULT 0.0,'
            '    `last_ffe_upload` FLOAT NOT NULL DEFAULT 0.0,'
            '    `last_ffe_rules_upload` FLOAT NOT NULL DEFAULT 0.0,'
            '    `last_chessevent_download_md5` TEXT,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    UNIQUE(`uniq_id`)'
            ')'
        )
        self.database.execute(
            'INSERT INTO `tournament`('
            '    `id`, '
            '    `uniq_id`, '
            '    `name`, '
            '    `path`, '
            '    `filename`, '
            '    `ffe_id`, '
            '    `ffe_password`,'
            '    `time_control_initial_time`, '
            '    `time_control_increment`, '
            '    `time_control_handicap_penalty_step`, '
            '    `time_control_handicap_penalty_value`, '
            '    `time_control_handicap_min_time`, '
            '    `chessevent_user_id`, '
            '    `chessevent_password`, '
            '    `chessevent_event_id`, '
            '    `chessevent_tournament_name`, '
            '    `record_illegal_moves`, '
            '    `rules`, '
            '    `check_in_open`, '
            '    `last_update`, '
            '    `last_illegal_move_update`, '
            '    `last_result_update`, '
            '    `last_check_in_update`, '
            '    `last_ffe_upload`, '
            '    `last_ffe_rules_upload`, '
            '    `last_chessevent_download_md5`'
            ') SELECT'
            '    `id`, '
            '    `uniq_id`, '
            '    `name`, '
            '    `path`, '
            '    `filename`, '
            '    `ffe_id`, '
            '    `ffe_password`,'
            '    `time_control_initial_time`,'
            '    `time_control_increment`,'
            '    `time_control_handicap_penalty_step`,'
            '    `time_control_handicap_penalty_value`,'
            '    `time_control_handicap_min_time`,'
            '    NULL,'
            '    NULL,'
            '    NULL,'
            '    `chessevent_tournament_name`,'
            '    `record_illegal_moves`,'
            '    `rules`,'
            '    `check_in_open`,'
            '    `last_update`,'
            '    `last_illegal_move_update`,'
            '    `last_result_update`,'
            '    `last_check_in_update`,'
            '    `last_ffe_upload`,'
            '    `last_ffe_rules_upload`,'
            '    `last_chessevent_download_md5`'
            'FROM `tournament_copy`'
        )
        self.database.execute('DROP TABLE `tournament_copy`')
        self.database.execute('PRAGMA foreign_keys=on')
        # Eventually drop the now useless chessevent table
        self.database.execute('DROP TABLE `chessevent`')
