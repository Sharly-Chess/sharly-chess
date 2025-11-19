from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'ALTER TABLE `tournament` ADD `index` INTEGER NOT NULL DEFAULT 0'
        )
        self.database.execute('SELECT id, name FROM tournament ORDER BY name')
        rows = self.database.fetchall()
        for idx, row in enumerate(rows):
            self.database.execute(
                'UPDATE tournament SET `index` = ? WHERE id = ?',
                (idx, row['id']),
            )

    def backward(self):
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `index`')
