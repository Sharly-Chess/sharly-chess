from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Lets the arbiter choose how the players with the same rating and
    title are ordered in the starting rank, with the seed of the drawing of
    lots when they are drawn."""

    def forward(self) -> None:
        self.database.execute(
            'ALTER TABLE `tournament` ADD `starting_rank_tie_order` '
            "TEXT NOT NULL DEFAULT 'ALPHABETICAL'"
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `starting_rank_lot_seed` INTEGER'
        )

    def backward(self) -> None:
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `starting_rank_lot_seed`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `starting_rank_tie_order`'
        )
