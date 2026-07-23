from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Add indexes used by tournament pairing and board queries."""

    def forward(self):
        self.database.execute(
            'CREATE INDEX IF NOT EXISTS `ix_pairing_board_id` ON `pairing`(`board_id`)'
        )
        self.database.execute(
            'CREATE INDEX IF NOT EXISTS `ix_pairing_tournament_player_round` '
            'ON `pairing`(`tournament_id`, `player_id`, `round`)'
        )
        self.database.execute(
            'CREATE INDEX IF NOT EXISTS `ix_pairing_tournament_board_round` '
            'ON `pairing`(`tournament_id`, `board_id`, `round`) '
            'WHERE `board_id` IS NOT NULL'
        )
        self.database.execute(
            'CREATE INDEX IF NOT EXISTS `ix_board_team_board_id` '
            'ON `board`(`team_board_id`)'
        )
        self.database.execute(
            'CREATE INDEX IF NOT EXISTS `ix_team_board_tournament_id` '
            'ON `team_board`(`tournament_id`)'
        )

    def backward(self):
        self.database.execute('DROP INDEX IF EXISTS `ix_pairing_board_id`')
        self.database.execute(
            'DROP INDEX IF EXISTS `ix_pairing_tournament_player_round`'
        )
        self.database.execute(
            'DROP INDEX IF EXISTS `ix_pairing_tournament_board_round`'
        )
        self.database.execute('DROP INDEX IF EXISTS `ix_board_team_board_id`')
        self.database.execute('DROP INDEX IF EXISTS `ix_team_board_tournament_id`')
