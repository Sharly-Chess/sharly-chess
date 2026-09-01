from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Record a knock-out's manually designated match winners: the team that
    advances from a level team match, and the player from a drawn individual
    game, when no computed tie-break settles it."""

    def forward(self):
        self.database.execute(
            'ALTER TABLE `team_board` ADD `knockout_winner_team_id` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `board` ADD `knockout_winner_player_id` INTEGER'
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `team_board` DROP COLUMN `knockout_winner_team_id`'
        )
        self.database.execute(
            'ALTER TABLE `board` DROP COLUMN `knockout_winner_player_id`'
        )
