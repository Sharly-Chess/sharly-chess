import json
from typing import Any

from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'CREATE TABLE `tie_break` ('
            '   `id` INTEGER NOT NULL,'
            '   `tournament_id` INTEGER NOT NULL,'
            '   `type` TEXT NOT NULL,'
            '   `options` TEXT NOT NULL,'
            '   `index` INTEGER NOT NULL,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`tournament_id`) REFERENCES '
            '   `tournament`(`id`) ON DELETE CASCADE'
            ')'
        )
        self.database.execute('SELECT `id`, `tie_breaks` FROM `tournament`')
        removed_option_ids = ['CUT', 'CUT_TOP', 'CUT_BOTTOM', 'LIMIT']
        for row in self.database.fetchall():
            tie_breaks = json.loads(row['tie_breaks'] or '[]')
            for index, tie_break in enumerate(tie_breaks):
                options = tie_break['options']
                for option_id in removed_option_ids:
                    # Only default options were added, no need to convert the options.
                    if option_id in options:
                        del options[option_id]
                fields = {
                    'tournament_id': row['id'],
                    'type': tie_break['type'],
                    'options': json.dumps(options),
                    'index': index,
                }
                fields_str = ', '.join(f'`{field}`' for field in fields)
                self.database.execute(
                    f'INSERT INTO `tie_break` ({fields_str}) '
                    f'VALUES ({", ".join(["?"] * len(fields))})',
                    tuple(fields.values()),
                )
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `tie_breaks`')

    def backward(self):
        self.database.execute(
            "ALTER TABLE `tournament` ADD `tie_breaks` TEXT NOT NULL DEFAULT '[]'"
        )
        self.database.execute('SELECT `id` FROM `tournament`')
        for row in self.database.fetchall():
            tournament_id = row['id']
            self.database.execute(
                'SELECT * FROM `tie_break` WHERE `tournament_id` = ? ORDER BY `index`',
                (tournament_id,),
            )
            tie_breaks: list[dict[str, Any]] = []
            for row_ in self.database.fetchall():
                tie_breaks.append(
                    {
                        'type': row_['type'],
                        'options': json.loads(row_['options']),
                    }
                )
            self.database.execute(
                'UPDATE `tournament` SET `tie_breaks` = ? WHERE `id` = ?',
                (json.dumps(tie_breaks), tournament_id),
            )

        self.database.execute('DROP TABLE `tie_break`')
