from datetime import date

from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        min_yob = 1900
        max_yob = date.today().year
        self.database.execute(
            'UPDATE `player` SET `year_of_birth` = NULL '
            'WHERE `year_of_birth` IS NOT NULL AND '
            'NOT (`year_of_birth` BETWEEN ? AND ?)',
            (min_yob, max_yob),
        )
        self.database.execute(
            'UPDATE `player` SET `date_of_birth` = NULL '
            'WHERE `date_of_birth` IS NOT NULL AND '
            "NOT (CAST(strftime('%Y', `date_of_birth`) AS INTEGER) BETWEEN ? AND ?)",
            (min_yob, max_yob),
        )

    def backward(self):
        pass
