from datetime import datetime

from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `timer_hour` ADD `triggered_at` TEXT')
        self.database.execute(
            'SELECT `id`, `uniq_id`, `timer_id`, `date_str`, `time_str` '
            'FROM `timer_hour` ORDER BY `timer_id`, `order`'
        )
        invalid_hour_ids: list[int] = []
        previous_timer_id = 0
        previous_datetime: datetime | None = None
        for row in self.database.fetchall():
            id_ = row['id']
            timer_id = row['timer_id']
            date_str = row['date_str']
            if not row['uniq_id']:
                invalid_hour_ids.append(id_)
                continue
            time = datetime.strptime(row['time_str'], '%H:%M').time()
            if timer_id != previous_timer_id:
                previous_timer_id = timer_id
                previous_datetime = None
            if not date_str:
                if previous_datetime is None:
                    invalid_hour_ids.append(id_)
                    continue
                current_datetime = datetime.combine(previous_datetime, time)
            else:
                current_datetime = datetime.combine(
                    datetime.strptime(date_str, '%Y-%m-%d'), time
                )
            if previous_datetime and current_datetime < previous_datetime:
                invalid_hour_ids.append(id_)
                continue
            previous_datetime = current_datetime
            self.database.execute(
                'UPDATE `timer_hour` SET `triggered_at` = ? WHERE `id` = ?',
                (current_datetime.strftime('%Y-%m-%dT%H:%M'), id_),
            )

        if invalid_hour_ids:
            query_list = ', '.join(['?'] * len(invalid_hour_ids))
            self.database.execute(
                f'DELETE FROM `timer_hour` WHERE `id` IN ({query_list})',
                tuple(invalid_hour_ids),
            )

        self.database.execute('ALTER TABLE `timer_hour` DROP COLUMN `order`')
        self.database.execute('ALTER TABLE `timer_hour` DROP COLUMN `date_str`')
        self.database.execute('ALTER TABLE `timer_hour` DROP COLUMN `time_str`')

    def backward(self):
        self.database.execute('ALTER TABLE `timer_hour` ADD `order` INTEGER')
        self.database.execute('ALTER TABLE `timer_hour` ADD `date_str` TEXT')
        self.database.execute('ALTER TABLE `timer_hour` ADD `time_str` TEXT')
        self.database.execute(
            'SELECT `id`, `timer_id`, `triggered_at` '
            'FROM `timer_hour` ORDER BY `timer_id`, `triggered_at`'
        )
        order = 0
        previous_timer_id = 0
        for row in self.database.fetchall():
            id_ = row['id']
            timer_id = row['timer_id']
            date_and_time = datetime.strptime(row['triggered_at'], '%Y-%m-%dT%H:%M')
            if timer_id != previous_timer_id:
                previous_timer_id = timer_id
                order = 0
            self.database.execute(
                'UPDATE `timer_hour` SET '
                '`order` = ?, `date_str` = ?, `time_str` = ?'
                'WHERE `id` = ?',
                (
                    order,
                    date_and_time.strftime('%Y-%m-%d'),
                    date_and_time.strftime('%H:%M'),
                    id_,
                ),
            )

        self.database.execute('ALTER TABLE `timer_hour` DROP COLUMN `triggered_at`')
