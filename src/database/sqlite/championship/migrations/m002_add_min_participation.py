from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        # Minimum number of source tournaments a competitor must have played in
        # to appear in the rankings (0 = no minimum).
        self.database.execute(
            'ALTER TABLE `info` '
            'ADD COLUMN `min_participation` INTEGER NOT NULL DEFAULT 0'
        )

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `min_participation`')
