from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Let a team be pinned to a table number, as a player can be in an
    individual tournament. The match keeps that table across rounds; its
    number is written onto the team board's index when the round is paired,
    so later changes don't renumber rounds already played.
    """

    def forward(self) -> None:
        self.database.execute('ALTER TABLE `team` ADD `fixed` INT')

    def backward(self) -> None:
        self.database.execute('ALTER TABLE `team` DROP COLUMN `fixed`')
