import json

from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'CREATE TABLE `rotating_screen` ('
            '   `id` INTEGER NOT NULL,'
            '   `rotator_id` INTEGER NOT NULL,'
            '   `screen_id` INTEGER,'
            '   `family_id` INTEGER,'
            '   `index` INTEGER NOT NULL,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`rotator_id`) REFERENCES '
            '   `rotator`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`screen_id`) REFERENCES '
            '   `screen`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`family_id`) REFERENCES '
            '   `family`(`id`) ON DELETE CASCADE'
            ')'
        )

        self.database.execute('SELECT `id`, `screen_ids`, `family_ids` FROM `rotator`')
        for row in self.database.fetchall():
            rotator_id = row['id']

            # Screens
            screen_ids = json.loads(row['screen_ids'])
            self.database.execute(
                'SELECT `id` FROM `screen` '
                f'WHERE `id` IN ({", ".join(["?"] * len(screen_ids))}) '
                'AND `type` != ? '
                'ORDER BY `uniq_id`',
                tuple(screen_ids + ['input']),
            )
            for index, row_ in enumerate(self.database.fetchall()):
                fields = {
                    'rotator_id': rotator_id,
                    'screen_id': row_['id'],
                    'index': index,
                }
                fields_str = ', '.join(f'`{field}`' for field in fields)
                self.database.execute(
                    f'INSERT INTO `rotating_screen` ({fields_str}) '
                    f'VALUES ({", ".join(["?"] * len(fields))})',
                    tuple(fields.values()),
                )

            # Families
            family_ids = json.loads(row['family_ids'])
            self.database.execute(
                'SELECT `id` FROM `family` '
                f'WHERE `id` IN ({", ".join(["?"] * len(family_ids))}) '
                'AND `type` != ? '
                'ORDER BY `uniq_id`',
                tuple(family_ids + ['input']),
            )
            for index, row_ in enumerate(self.database.fetchall()):
                fields = {
                    'rotator_id': rotator_id,
                    'family_id': row_['id'],
                    'index': index,
                }
                fields_str = ', '.join(f'`{field}`' for field in fields)
                self.database.execute(
                    f'INSERT INTO `rotating_screen` ({fields_str}) '
                    f'VALUES ({", ".join(["?"] * len(fields))})',
                    tuple(fields.values()),
                )

        self.database.execute('ALTER TABLE `rotator` DROP COLUMN `screen_ids`')
        self.database.execute('ALTER TABLE `rotator` DROP COLUMN `family_ids`')

    def backward(self):
        self.database.execute('ALTER TABLE `rotator` ADD `screen_ids` TEXT')
        self.database.execute('ALTER TABLE `rotator` ADD `family_ids` TEXT')

        self.database.execute('SELECT `id` FROM `rotator`')
        for row in self.database.fetchall():
            rotator_id = row['id']
            self.database.execute(
                'SELECT * FROM `rotating_screen` '
                'WHERE `rotator_id` = ? '
                'ORDER BY `index`',
                (rotator_id,),
            )
            screen_ids = []
            family_ids = []
            for row_ in self.database.fetchall():
                if screen_id := row_['screen_id']:
                    if screen_id not in screen_ids:
                        screen_ids.append(screen_id)
                elif family_id := row_['family_id']:
                    if family_id not in family_ids:
                        family_ids.append(family_id)

            self.database.execute(
                'UPDATE `rotator` SET `screen_ids` = ?, `family_ids` = ? WHERE `id` = ?',
                (json.dumps(screen_ids), json.dumps(family_ids), rotator_id),
            )

        self.database.execute('DROP TABLE `rotating_screen`')
