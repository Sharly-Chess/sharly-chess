from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """The replacement of a player who leaves a round-robin: the newcomer
    takes the seat of ``replaces_player_id`` from ``replaced_from_round``
    on, playing the opponents of the schedule in their place."""

    def forward(self) -> None:
        self.database.execute(
            'ALTER TABLE `tournament_player` ADD `replaces_player_id` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `tournament_player` ADD `replaced_from_round` INTEGER'
        )

    def backward(self) -> None:
        self.database.execute(
            'ALTER TABLE `tournament_player` DROP COLUMN `replaced_from_round`'
        )
        self.database.execute(
            'ALTER TABLE `tournament_player` DROP COLUMN `replaces_player_id`'
        )
