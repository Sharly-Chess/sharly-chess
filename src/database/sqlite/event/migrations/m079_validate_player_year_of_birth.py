from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'UPDATE `player` SET `year_of_birth` = NULL '
            'WHERE `year_of_birth` IS NOT NULL AND '
            'NOT (`year_of_birth` BETWEEN 1900 AND 2026)'
        )
        self.database.execute(
            'UPDATE `player` SET `date_of_birth` = NULL '
            'WHERE `date_of_birth` IS NOT NULL AND '
            "NOT (CAST(strftime('%Y', `date_of_birth`) AS INTEGER) BETWEEN 1900 AND 2026)"
        )

    def backward(self):
        pass
