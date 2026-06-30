import json

from database.sqlite.migration import BaseMigration


# Result enum values used by the migration. Keep in sync with utils.enum.Result.
_RESULT_LOSS = 1
_RESULT_DRAW = 2
_RESULT_WIN = 3
_RESULT_ZERO_POINT_BYE = 7
_RESULT_PAIRING_ALLOCATED_BYE = 9


def _initial_game_points(
    three_points_for_a_win: int | None,
    pab_value: int | None,
) -> str | None:
    """Build the migrated game_points override dict.
    Only non-default values are stored; returns None when defaults apply
    (1/0.5/0 game points, PAB worth a win)."""
    overrides: dict[int, float] = {}
    if three_points_for_a_win:
        overrides[_RESULT_WIN] = 3.0
        overrides[_RESULT_DRAW] = 1.0
        overrides[_RESULT_LOSS] = 0.0
        draw_pts = 1.0
        loss_pts = 0.0
    else:
        draw_pts = 0.5
        loss_pts = 0.0
    if pab_value == _RESULT_DRAW:
        overrides[_RESULT_PAIRING_ALLOCATED_BYE] = draw_pts
    elif pab_value == _RESULT_LOSS:
        overrides[_RESULT_PAIRING_ALLOCATED_BYE] = loss_pts
    # PAB defaulting to WIN value is the implicit default, no override needed.
    if not overrides:
        return None
    return json.dumps({str(k): v for k, v in overrides.items()})


class Migration(BaseMigration):
    @staticmethod
    def are_foreign_keys_enabled() -> bool:
        # The ``board`` table rebuild (relaxing ``white_player_id`` to
        # nullable for lineup-hole support) drops and renames the
        # table. ``pairing.board_id`` has ``ON DELETE CASCADE`` to
        # ``board.id`` — with FK enforcement on, the swap cascades
        # through and nukes every pairing row.
        return False

    def forward(self):
        # New tables
        # Event-level reusable team groupings (club / league / etc.).
        # A team references one by ``group_id``; used downstream to keep
        # teams in the same group from being paired together.
        self.database.execute(
            'CREATE TABLE `team_group` ('
            '   `id` INTEGER NOT NULL,'
            '   `name` TEXT NOT NULL,'
            '   PRIMARY KEY(`id` AUTOINCREMENT)'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `team` ('
            '   `id` INTEGER NOT NULL,'
            '   `tournament_id` INTEGER,'
            '   `name` TEXT NOT NULL,'
            '   `pairing_number` INTEGER,'
            '   `captain_id` INTEGER,'
            '   `captain_name` TEXT,'
            '   `group_id` INTEGER,'
            '   `federation` TEXT,'
            '   `check_in` INTEGER NOT NULL DEFAULT 0,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`tournament_id`) REFERENCES '
            '   `tournament`(`id`) ON DELETE SET NULL,'
            '   FOREIGN KEY (`captain_id`) REFERENCES '
            '   `player`(`id`) ON DELETE SET NULL,'
            '   FOREIGN KEY (`group_id`) REFERENCES '
            '   `team_group`(`id`) ON DELETE SET NULL'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `team_round_lineup` ('
            '   `team_id` INTEGER NOT NULL,'
            '   `round` INTEGER NOT NULL,'
            '   `player_id` INTEGER NOT NULL,'
            '   `index` INTEGER NOT NULL,'
            '   PRIMARY KEY (`team_id`, `round`, `index`),'
            '   FOREIGN KEY (`team_id`) REFERENCES '
            '   `team`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`player_id`) REFERENCES '
            '   `player`(`id`) ON DELETE CASCADE'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `team_board` ('
            '   `id` INTEGER NOT NULL,'
            '   `tournament_id` INTEGER NOT NULL,'
            '   `round` INTEGER NOT NULL,'
            '   `team_a_id` INTEGER NOT NULL,'
            '   `team_b_id` INTEGER,'
            # Table number slot (0-based). NULL for byes that don't sit
            # at a table — hidden byes (HPB / FPB / ZPB). Real matches
            # and the (displayed) PAB bye carry an index.
            '   `index` INTEGER,'
            '   `last_result_update` TEXT,'
            # Bye type when ``team_b_id`` is NULL (PAB / HPB / FPB / ZPB).
            # NULL for regular pairings.
            '   `bye_type` TEXT,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`tournament_id`) REFERENCES '
            '   `tournament`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`team_a_id`) REFERENCES '
            '   `team`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`team_b_id`) REFERENCES '
            '   `team`(`id`) ON DELETE CASCADE'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `team_pairing_block` ('
            '   `id` INTEGER NOT NULL,'
            '   `tournament_id` INTEGER NOT NULL,'
            '   `round` INTEGER,'
            '   `team_a_id` INTEGER NOT NULL,'
            '   `team_b_id` INTEGER NOT NULL,'
            '   `reason` TEXT,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`tournament_id`) REFERENCES '
            '   `tournament`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`team_a_id`) REFERENCES '
            '   `team`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`team_b_id`) REFERENCES '
            '   `team`(`id`) ON DELETE CASCADE'
            ')'
        )
        # Per-team, per-round bonus / penalty points (manual entry).
        # ``mp_delta`` / ``gp_delta`` may be negative. Rule-set
        # adjustments are computed live and are not stored here.
        self.database.execute(
            'CREATE TABLE `team_point_adjustment` ('
            '   `id` INTEGER NOT NULL,'
            '   `tournament_id` INTEGER NOT NULL,'
            '   `team_id` INTEGER NOT NULL,'
            '   `round` INTEGER NOT NULL,'
            '   `mp_delta` REAL NOT NULL DEFAULT 0,'
            '   `gp_delta` REAL NOT NULL DEFAULT 0,'
            '   `reason` TEXT,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`tournament_id`) REFERENCES '
            '   `tournament`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`team_id`) REFERENCES '
            '   `team`(`id`) ON DELETE CASCADE,'
            '   UNIQUE(`tournament_id`, `team_id`, `round`)'
            ')'
        )
        # Prohibited pairings. A group is a set of members (players or
        # teams) that must not be paired together. ``round`` NULL marks a
        # reusable manual template group (edited in the modal, carried
        # forward); a non-NULL ``round`` marks an immutable per-round
        # snapshot (manual + dimension-derived groups flattened) that
        # drives the TRF 260 export. ``is_hard`` distinguishes hard from
        # soft constraints. ``protect_rank`` (per-round snapshot rows only)
        # records the soft-relaxation cutoff chosen for that round: members
        # whose standing rank is ``<= protect_rank`` kept all their soft
        # separations. It lets the export regenerate the exact applied 260
        # set without persisting the (potentially huge) pairwise expansion.
        self.database.execute(
            'CREATE TABLE `prohibited_pairing_group` ('
            '   `id` INTEGER NOT NULL,'
            '   `tournament_id` INTEGER NOT NULL,'
            '   `round` INTEGER,'
            '   `is_hard` INTEGER NOT NULL DEFAULT 1,'
            '   `protect_rank` INTEGER,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`tournament_id`) REFERENCES '
            '   `tournament`(`id`) ON DELETE CASCADE'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `prohibited_pairing_group_member` ('
            '   `group_id` INTEGER NOT NULL,'
            '   `member_id` INTEGER NOT NULL,'
            '   PRIMARY KEY(`group_id`, `member_id`),'
            '   FOREIGN KEY (`group_id`) REFERENCES '
            '   `prohibited_pairing_group`(`id`) ON DELETE CASCADE'
            ')'
        )

        # ALTER existing tables
        self.database.execute(
            "ALTER TABLE `info` ADD `event_type` TEXT NOT NULL DEFAULT 'INDIVIDUAL'"
        )
        self.database.execute(
            'ALTER TABLE `player` ADD `team_id` INTEGER '
            'REFERENCES `team`(`id`) ON DELETE SET NULL'
        )
        self.database.execute('ALTER TABLE `player` ADD `team_index` INTEGER')

        # Rebuild ``board``: relax ``white_player_id`` to nullable
        # (so a team-match board can store a hole on the physical white
        # side, mirroring the already-nullable ``black_player_id``)
        # and add ``team_board_id`` linking each individual board to
        # its parent team match. ``delete_board_on_pairing_delete``
        # (m038) references ``board`` so it has to come down before
        # the rename swap.
        self.database.execute('DROP TRIGGER IF EXISTS `delete_board_on_pairing_delete`')
        self.database.execute(
            'CREATE TABLE `board_new` ('
            '   `id` INTEGER NOT NULL,'
            '   `white_player_id` INTEGER,'
            '   `black_player_id` INTEGER,'
            '   `index` INTEGER NOT NULL,'
            '   `last_result_update` FLOAT,'
            '   `team_board_id` INTEGER,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`white_player_id`) REFERENCES '
            '   `player`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`black_player_id`) REFERENCES '
            '   `player`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`team_board_id`) REFERENCES '
            '   `team_board`(`id`) ON DELETE SET NULL'
            ')'
        )
        self.database.execute(
            'INSERT INTO `board_new` '
            '(`id`, `white_player_id`, `black_player_id`, '
            '`index`, `last_result_update`) '
            'SELECT `id`, `white_player_id`, `black_player_id`, '
            '`index`, `last_result_update` '
            'FROM `board`'
        )
        self.database.execute('DROP TABLE `board`')
        self.database.execute('ALTER TABLE `board_new` RENAME TO `board`')
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `delete_board_on_pairing_delete`
            AFTER DELETE ON `pairing`
            BEGIN
                DELETE FROM `board`
                WHERE `id` = `OLD`.`board_id`;
            END;
            """
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `team_player_count` INTEGER'
        )
        self.database.execute('ALTER TABLE `tournament` ADD `roster_max_size` INTEGER')
        self.database.execute('ALTER TABLE `tournament` ADD `match_points` TEXT')
        self.database.execute('ALTER TABLE `tournament` ADD `color_pattern` TEXT')
        self.database.execute('ALTER TABLE `tournament` ADD `primary_score` TEXT')
        self.database.execute('ALTER TABLE `tournament` ADD `secondary_score` TEXT')
        self.database.execute('ALTER TABLE `tournament` ADD `team_colour_type` TEXT')
        self.database.execute(
            'ALTER TABLE `tournament` ADD `enforce_roster_order` '
            'INTEGER NOT NULL DEFAULT 0'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `team_sort_mode` '
            "TEXT NOT NULL DEFAULT 'MANUAL'"
        )
        self.database.execute('ALTER TABLE `tournament` ADD `rule_set` TEXT')
        # Prohibited-pairings config: the chosen grouping dimension id
        # (NULL = off) and whether it's a hard constraint.
        self.database.execute(
            'ALTER TABLE `tournament` ADD `prohibited_pairing_dimension` TEXT'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `prohibited_pairing_dimension_is_hard` '
            'INTEGER NOT NULL DEFAULT 1'
        )
        self.database.execute('ALTER TABLE `pairing` ADD `effective_points` REAL')

        # Replace three_points_for_a_win/pab_value with a single game_points JSON
        # column covering WIN, DRAW, LOSS, ZERO_POINT_BYE, PAIRING_ALLOCATED_BYE.
        self.database.execute('ALTER TABLE `tournament` ADD `game_points` TEXT')
        self.database.execute(
            'SELECT `id`, `three_points_for_a_win`, `pab_value` FROM `tournament`'
        )
        for row in self.database.fetchall():
            self.database.execute(
                'UPDATE `tournament` SET `game_points` = ? WHERE `id` = ?',
                (
                    _initial_game_points(
                        row['three_points_for_a_win'], row['pab_value']
                    ),
                    row['id'],
                ),
            )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `three_points_for_a_win`'
        )
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `pab_value`')

        # Fix historical check-in screen column-display bug: check-in screens
        # always rendered 2 visual columns per logical column due to tuple-splitting
        # in templates. Double the configured column count for existing check-in
        # screens (and families) so they keep their visual appearance. A NULL
        # column count means the default of 1 logical column, which also displayed
        # as 2, so it is doubled too.
        self.database.execute(
            'UPDATE `screen` SET `columns` = COALESCE(`columns`, 1) * 2 '
            "WHERE `type` = 'check-in'"
        )
        self.database.execute(
            'UPDATE `family` SET `columns` = COALESCE(`columns`, 1) * 2 '
            "WHERE `type` = 'check-in'"
        )

    def backward(self):
        # Reverse the check-in column doubling
        self.database.execute(
            "UPDATE `screen` SET `columns` = `columns` / 2 WHERE `type` = 'check-in'"
        )
        self.database.execute(
            "UPDATE `family` SET `columns` = `columns` / 2 WHERE `type` = 'check-in'"
        )

        self.database.execute('ALTER TABLE `pairing` DROP COLUMN `effective_points`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `team_colour_type`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `secondary_score`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `primary_score`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `color_pattern`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `match_points`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `roster_max_size`')
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `team_player_count`'
        )
        # Rebuild ``board`` to undo the nullable-white relaxation and
        # drop ``team_board_id``. Rows with NULL white_player_id can't
        # be represented in the rolled-back world — drop them.
        self.database.execute('DROP TRIGGER IF EXISTS `delete_board_on_pairing_delete`')
        self.database.execute(
            'CREATE TABLE `board_new` ('
            '   `id` INTEGER NOT NULL,'
            '   `white_player_id` INTEGER NOT NULL,'
            '   `black_player_id` INTEGER,'
            '   `index` INTEGER NOT NULL,'
            '   `last_result_update` FLOAT,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`white_player_id`) REFERENCES '
            '   `player`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`black_player_id`) REFERENCES '
            '   `player`(`id`) ON DELETE CASCADE'
            ')'
        )
        self.database.execute(
            'INSERT INTO `board_new` '
            '(`id`, `white_player_id`, `black_player_id`, '
            '`index`, `last_result_update`) '
            'SELECT `id`, `white_player_id`, `black_player_id`, '
            '`index`, `last_result_update` '
            'FROM `board` WHERE `white_player_id` IS NOT NULL'
        )
        self.database.execute('DROP TABLE `board`')
        self.database.execute('ALTER TABLE `board_new` RENAME TO `board`')
        self.database.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                `delete_board_on_pairing_delete`
            AFTER DELETE ON `pairing`
            BEGIN
                DELETE FROM `board`
                WHERE `id` = `OLD`.`board_id`;
            END;
            """
        )
        self.database.execute('ALTER TABLE `player` DROP COLUMN `team_index`')
        self.database.execute('ALTER TABLE `player` DROP COLUMN `team_id`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `event_type`')

        self.database.execute('DROP TABLE `team_pairing_block`')
        self.database.execute('DROP TABLE `team_board`')
        self.database.execute('DROP TABLE `team_round_lineup`')
        self.database.execute('DROP TABLE `team`')

        # Restore old columns, populating from game_points before dropping it.
        self.database.execute(
            'ALTER TABLE `tournament` ADD `three_points_for_a_win` '
            'INTEGER NOT NULL DEFAULT 0'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `pab_value` INTEGER NOT NULL DEFAULT 3'
        )
        self.database.execute('SELECT `id`, `game_points` FROM `tournament`')
        rows = self.database.fetchall()
        for row in rows:
            game_points = row['game_points']
            if not game_points:
                continue
            data = json.loads(game_points)
            win_pts = float(data.get(str(_RESULT_WIN), 1.0))
            draw_pts = float(data.get(str(_RESULT_DRAW), 0.5))
            loss_pts = float(data.get(str(_RESULT_LOSS), 0.0))
            pab_pts = float(data.get(str(_RESULT_PAIRING_ALLOCATED_BYE), win_pts))
            three_pts = 1 if win_pts == 3.0 else 0
            if pab_pts == win_pts:
                pab = _RESULT_WIN
            elif pab_pts == draw_pts:
                pab = _RESULT_DRAW
            elif pab_pts == loss_pts:
                pab = _RESULT_LOSS
            else:
                pab = _RESULT_WIN
            self.database.execute(
                'UPDATE `tournament` SET `three_points_for_a_win` = ?, '
                '`pab_value` = ? WHERE `id` = ?',
                (three_pts, pab, row['id']),
            )
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `game_points`')
