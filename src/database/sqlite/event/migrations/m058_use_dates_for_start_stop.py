from datetime import datetime

from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    @staticmethod
    def timestamp_to_date(timestamp: float | None) -> str | None:
        if not timestamp:
            return None
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')

    @staticmethod
    def date_to_timestamp(date: str | None) -> float | None:
        if not date:
            return None
        return datetime.strptime(date, '%Y-%m-%d').timestamp()

    def forward(self):
        # Event
        self.database.execute('ALTER TABLE `info` ADD `start_date` TEXT')
        self.database.execute('ALTER TABLE `info` ADD `stop_date` TEXT')
        self.database.execute('SELECT `start`, `stop` FROM `info`')
        row = self.database.fetchone()
        self.database.execute(
            'UPDATE `info` SET `start_date` = ?, `stop_date` = ?',
            (
                self.timestamp_to_date(row['start']),
                self.timestamp_to_date(row['stop']),
            ),
        )
        self.database.execute('ALTER TABLE `info` DROP COLUMN `start`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `stop`')

        # Tournaments
        self.database.execute('ALTER TABLE `tournament` ADD `start_date` TEXT')
        self.database.execute('ALTER TABLE `tournament` ADD `stop_date` TEXT')
        self.database.execute('SELECT `id`, `start`, `stop` FROM `tournament`')
        for row in self.database.fetchall():
            self.database.execute(
                'UPDATE `tournament` SET '
                '`start_date` = ?, `stop_date` = ? WHERE `id` = ?',
                (
                    self.timestamp_to_date(row['start']),
                    self.timestamp_to_date(row['stop']),
                    row['id'],
                ),
            )
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `start`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `stop`')

    def backward(self):
        # Event
        self.database.execute('ALTER TABLE `info` ADD `start` FLOAT')
        self.database.execute('ALTER TABLE `info` ADD `stop` FLOAT')
        self.database.execute('SELECT `start_date`, `stop_date` FROM `info`')
        row = self.database.fetchone()
        self.database.execute(
            'UPDATE `info` SET `start` = ?, `stop` = ?',
            (
                self.date_to_timestamp(row['start_date']),
                self.date_to_timestamp(row['stop_date']),
            ),
        )
        self.database.execute('ALTER TABLE `info` DROP COLUMN `start_date`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `stop_date`')

        # Tournaments
        self.database.execute('ALTER TABLE `tournament` ADD `start` FLOAT')
        self.database.execute('ALTER TABLE `tournament` ADD `stop` FLOAT')
        self.database.execute(
            'SELECT `id`, `start_date`, `stop_date` FROM `tournament`'
        )
        for row in self.database.fetchall():
            self.database.execute(
                'UPDATE `tournament` SET `start` = ?, `stop` = ? WHERE `id` = ?',
                (
                    self.date_to_timestamp(row['start_date']),
                    self.date_to_timestamp(row['stop_date']),
                    row['id'],
                ),
            )
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `start_date`')
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `stop`')
