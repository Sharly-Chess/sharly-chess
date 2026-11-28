from database.sqlite.migration import BaseMigration

_TRIGGERS = {
    'insert': ('INSERT', 'NEW'),
    'update': ('UPDATE', 'NEW'),
    'delete': ('DELETE', 'OLD'),
}


class Migration(BaseMigration):
    """The results of the games a team match counts beyond its boards,
    which the rule set of the tournament declares. A game is known by its
    round and its two players; ``result`` is that of white."""

    def forward(self) -> None:
        self.database.execute(
            'CREATE TABLE `extra_game` ('
            '   `id` INTEGER NOT NULL,'
            '   `tournament_id` INTEGER NOT NULL,'
            '   `round` INTEGER NOT NULL,'
            '   `white_player_id` INTEGER NOT NULL,'
            '   `black_player_id` INTEGER NOT NULL,'
            '   `result` INTEGER NOT NULL,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`tournament_id`) REFERENCES '
            '   `tournament`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`white_player_id`) REFERENCES '
            '   `player`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`black_player_id`) REFERENCES '
            '   `player`(`id`) ON DELETE CASCADE,'
            '   UNIQUE(`tournament_id`, `round`, `white_player_id`, '
            '   `black_player_id`)'
            ')'
        )
        for name, (action, row) in _TRIGGERS.items():
            self.database.execute(
                f"""
                CREATE TRIGGER `set_tournament_last_pairing_update_on_extra_game_{name}`
                AFTER {action} ON `extra_game`
                BEGIN
                    UPDATE `tournament`
                    SET `last_pairing_update` = strftime('%Y-%m-%d %H:%M:%f', 'now') || '+00:00'
                    WHERE `id` = `{row}`.`tournament_id`;
                END;
                """
            )

    def backward(self) -> None:
        for name in _TRIGGERS:
            self.database.execute(
                f'DROP TRIGGER `set_tournament_last_pairing_update_on_extra_game_{name}`'
            )
        self.database.execute('DROP TABLE `extra_game`')
