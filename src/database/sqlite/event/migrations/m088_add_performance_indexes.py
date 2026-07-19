from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Index the pairing / board hot paths.

    Loading a large event was dominated by ``load_tournament_stored_boards_by_round``
    (a ``board``/``pairing`` join) and the per-round pairing scans, all against a
    ``pairing`` table with no indexes. The same composite index also covers the
    ``WHERE tournament_id = ? AND player_id = ? AND round = ?`` used when a result
    is entered."""

    def forward(self):
        self.database.execute(
            'CREATE INDEX IF NOT EXISTS `ix_pairing_board_id` ON `pairing`(`board_id`)'
        )
        self.database.execute(
            'CREATE INDEX IF NOT EXISTS `ix_pairing_tournament_player_round` '
            'ON `pairing`(`tournament_id`, `player_id`, `round`)'
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
        self.database.execute('DROP INDEX IF EXISTS `ix_board_team_board_id`')
        self.database.execute('DROP INDEX IF EXISTS `ix_team_board_tournament_id`')
