from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'CREATE TABLE `info` ('
            "    `name` TEXT NOT NULL DEFAULT '',"
            "    `competitor_type` TEXT NOT NULL DEFAULT 'INDIVIDUAL',"
            "    `team_score_basis` TEXT NOT NULL DEFAULT 'SOURCE_PRIMARY',"
            '    `age_category_base_date` TEXT'
            ')'
        )
        self.database.execute('INSERT INTO `info` DEFAULT VALUES')
        # A referenced tournament belonging to an independent event. The event
        # is identified by its uniq_id (file stem) and the tournament by its id
        # within that event. Snapshot columns keep a readable label when the
        # source can no longer be resolved (event/tournament deleted).
        # `coefficient` weights a stage: its points and tie-break values are
        # multiplied by it when aggregated (e.g. a final counting double).
        self.database.execute(
            'CREATE TABLE `source` ('
            '    `id` INTEGER NOT NULL,'
            '    `index` INTEGER NOT NULL DEFAULT 0,'
            '    `event_uniq_id` TEXT NOT NULL,'
            '    `tournament_id` INTEGER NOT NULL,'
            '    `event_name` TEXT,'
            '    `tournament_name` TEXT,'
            '    `start_date` TEXT,'
            '    `stop_date` TEXT,'
            '    `coefficient` REAL NOT NULL DEFAULT 1.0,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    UNIQUE(`event_uniq_id`, `tournament_id`)'
            ')'
        )
        # Manual identity override. Players are matched across sources live (by
        # fide id / name+birth / plugin key); an override pins a source player to
        # a named group so the organiser can merge participants the automatic
        # match missed (typo, missing fide id). ``group_key`` acts as an extra
        # identity key: participants sharing one are forced into the same player.
        self.database.execute(
            'CREATE TABLE `player_override` ('
            '    `id` INTEGER NOT NULL,'
            '    `event_uniq_id` TEXT NOT NULL,'
            '    `tournament_id` INTEGER NOT NULL,'
            '    `source_player_id` INTEGER NOT NULL,'
            '    `group_key` TEXT NOT NULL,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    UNIQUE(`event_uniq_id`, `tournament_id`, `source_player_id`)'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `team_override` ('
            '    `id` INTEGER NOT NULL,'
            '    `event_uniq_id` TEXT NOT NULL,'
            '    `tournament_id` INTEGER NOT NULL,'
            '    `source_team_id` INTEGER NOT NULL,'
            '    `group_key` TEXT NOT NULL,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    UNIQUE(`event_uniq_id`, `tournament_id`, `source_team_id`)'
            ')'
        )
        # Ordered championship scoring rules. Each is a criterion applied in
        # `index` order to rank the reconciled competitors (the first is the
        # main score, the rest are tie breaks). `best_n` scopes a rule to the
        # competitor's best N stages by points (NULL = all stages). `options`
        # carries rule-specific configuration (e.g. an F1 points table, or the
        # source tie-break a "sum/average of tie-break" rule reads).
        self.database.execute(
            'CREATE TABLE `championship_rule` ('
            '    `id` INTEGER NOT NULL,'
            '    `index` INTEGER NOT NULL DEFAULT 0,'
            '    `type` TEXT NOT NULL,'
            '    `best_n` INTEGER,'
            "    `options` TEXT NOT NULL DEFAULT '{}',"
            '    PRIMARY KEY(`id` AUTOINCREMENT)'
            ')'
        )
        # Named category standings. Criteria deliberately mirror prize player
        # filters so built-in and plugin-provided filters share one vocabulary.
        self.database.execute(
            'CREATE TABLE `championship_category` ('
            '    `id` INTEGER NOT NULL,'
            '    `name` TEXT NOT NULL,'
            '    `index` INTEGER NOT NULL DEFAULT 0,'
            '    PRIMARY KEY(`id` AUTOINCREMENT)'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `championship_criterion` ('
            '    `id` INTEGER NOT NULL,'
            '    `championship_category_id` INTEGER NOT NULL,'
            '    `type` TEXT NOT NULL,'
            "    `options` TEXT NOT NULL DEFAULT '{}',"
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    FOREIGN KEY (`championship_category_id`) REFERENCES '
            '        `championship_category`(`id`) ON DELETE CASCADE'
            ')'
        )
        # Manual tie-break: a pinned position for a reconciled competitor, set by
        # dragging it in the ranking. `competitor_key` is the stable identity
        # derived from the competitor's source participations; `position` orders
        # the still-tied competitors (higher = better).
        self.database.execute(
            'CREATE TABLE `championship_manual_tiebreak` ('
            '    `competitor_key` TEXT NOT NULL,'
            '    `position` INTEGER NOT NULL,'
            '    PRIMARY KEY(`competitor_key`)'
            ')'
        )

    def backward(self):
        self.database.execute('DROP TABLE `championship_manual_tiebreak`')
        self.database.execute('DROP TABLE `championship_criterion`')
        self.database.execute('DROP TABLE `championship_category`')
        self.database.execute('DROP TABLE `championship_rule`')
        self.database.execute('DROP TABLE `team_override`')
        self.database.execute('DROP TABLE `player_override`')
        self.database.execute('DROP TABLE `source`')
        self.database.execute('DROP TABLE `info`')
