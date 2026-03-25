from datetime import date

from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('SELECT start_date, stop_date FROM info')
        row = self.database.fetchone()
        start_date = row['start_date']
        stop_date = row['stop_date']
        self.database.execute(
            'UPDATE tournament SET start_date=?, stop_date=? '
            'WHERE start_date IS NULL OR stop_date IS NULL',
            (start_date, stop_date),
        )
        self.database.execute('ALTER TABLE `info` DROP COLUMN `start_date`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `stop_date`')

    def backward(self):
        self.database.execute('ALTER TABLE `info` ADD `start_date` TEXT')
        self.database.execute('ALTER TABLE `info` ADD `stop_date` TEXT')

        today = date.today().strftime('%Y-%m-%d')
        self.database.execute(
            'UPDATE info SET '
            '   start_date=(SELECT IFNULL(MIN(t1.start_date), ?)  FROM tournament t1), '
            '   stop_date=(SELECT IFNULL(MAX(t2.stop_date), ?) FROM tournament t2)',
            (today, today),
        )
