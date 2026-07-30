from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Adds a `ranking_basis` to prize categories: the order in which a
    category ranks its eligible players before prizes are assigned (final
    standing, average per-round performance or best single-round performance).
    Existing categories keep the historic behaviour (final standing)."""

    def forward(self):
        self.database.execute(
            'ALTER TABLE `prize_category` '
            "ADD `ranking_basis` TEXT NOT NULL DEFAULT 'final_standing'"
        )

    def backward(self):
        self.database.execute(
            'ALTER TABLE `prize_category` DROP COLUMN `ranking_basis`'
        )
