import json
from collections import defaultdict
from typing import Any

from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    @staticmethod
    def _get_new_criterion(
        old_id: str, options: dict[str, Any]
    ) -> tuple[str, Any | None]:
        new_id = old_id.lower().replace('-', '_')
        value: Any | None = None
        match old_id:
            case 'GENDER':
                value = options.get('GENDER_VALUE')
            case 'RATING':
                value = {
                    'min': options.get('MIN_RATING'),
                    'max': options.get('MAX_RATING'),
                }
            case 'AGE':
                categories = sorted(
                    options.get('AGE_CATEGORIES', []),
                    key=lambda cat: (
                        cat.startswith('O'),
                        int(cat[1:]),
                    ),
                )
                new_id = 'age_category'
                value = {
                    'min': categories[0],
                    'max': categories[-1],
                }
                if options.get('AGE_LOWER'):
                    value['min'] = None
                elif options.get('AGE_GREATER'):
                    value['max'] = None
            case 'CLUB':
                clubs = options.get('CLUBS', [])
                if len(clubs) == 1 and not options.get('EXCLUDE'):
                    value = clubs[0]
            case 'FEDERATION':
                federations = options.get('FEDERATIONS', [])
                if len(federations) == 1 and not options.get('EXCLUDE'):
                    value = federations[0]
            case 'ffe-LICENCE':
                licences = options.get('ffe-LICENCES', [])
                value = 'A'
                if 'B' in licences:
                    value = 'B'
                elif 'N' in licences:
                    value = 'N'
            case 'ffe-LEAGUE':
                leagues = options.get('ffe-LEAGUES', [])
                if len(leagues) == 1 and not options.get('EXCLUDE'):
                    value = leagues[0]
        return new_id, value

    def forward(self):
        self.database.execute(
            "ALTER TABLE `tournament` ADD `criteria` TEXT NOT NULL DEFAULT '{}'"
        )
        criteria_by_tournament_id: dict[int, dict[str, Any]] = defaultdict(dict)
        self.database.execute('SELECT * FROM `tournament_criterion`')
        for row in self.database.fetchall():
            criterion_id, value = self._get_new_criterion(
                row['type'], json.loads(row['options'])
            )
            if value is not None:
                criteria_by_tournament_id[row['tournament_id']][criterion_id] = value
        for tournament_id, criteria in criteria_by_tournament_id.items():
            self.database.execute(
                'UPDATE `tournament` SET `criteria` = ? WHERE `id` = ?',
                (json.dumps(criteria), tournament_id),
            )
        self.database.execute('DROP TABLE `tournament_criterion`')
        self.database.execute(
            'DELETE FROM `prize_criterion` WHERE `type` = ?', ('ffe-LICENCE',)
        )

    def _get_old_criterion(
        self, new_id: str, value: Any
    ) -> tuple[str, dict[str, Any] | None]:
        old_id = new_id.upper()
        options: dict[str, Any] | None = None
        match new_id:
            case 'gender':
                options = {'GENDER_VALUE': value}
            case 'rating':
                options = {
                    'RATING_MIN': value.get('min'),
                    'RATING_MAX': value.get('max'),
                }
            case 'age_category':
                old_id = 'AGE'
                min_category = value.get('min')
                max_category = value.get('max')
                if not (min_category and max_category) or min_category == max_category:
                    options = {
                        'AGE_CATEGORIES': [min_category or max_category],
                        'AGE_LOWER': not bool(min_category),
                        'AGE_GREATER': not bool(max_category),
                    }
            case 'club':
                options = {'CLUBS': [value], 'EXCLUDE': False}
            case 'federation':
                options = {'FEDERATIONS': [value], 'EXCLUDE': False}
            case 'ffe_licence':
                old_id = 'ffe-LICENCE'
                if value == 'A':
                    licences = ['A']
                elif value == 'B':
                    licences = ['N', 'B']
                else:
                    licences = ['N', 'B', 'A']
                options = {'ffe-LICENCES': licences}
            case 'ffe_league':
                old_id = 'ffe-LEAGUE'
                options = {'ffe-LEAGUES': [value], 'EXCLUDE': False}
        return old_id, options

    def backward(self):
        self.database.execute(
            'CREATE TABLE `tournament_criterion` ('
            '   `id` INTEGER NOT NULL,'
            '   `tournament_id` INTEGER NOT NULL,'
            '   `type` TEXT NOT NULL,'
            '   `options` TEXT,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   UNIQUE(`id`),'
            '   FOREIGN KEY (`tournament_id`) REFERENCES '
            '   `tournament`(`id`) ON DELETE CASCADE'
            ')'
        )
        self.database.execute('SELECT `id`, `criteria` FROM `tournament`')
        for row in self.database.fetchall():
            tournament_id = row['id']
            for new_id, value in json.loads(row['criteria']).items():
                old_id, options = self._get_old_criterion(new_id, value)
                if options is not None:
                    self.database.execute(
                        'INSERT INTO `tournament_criterion` ('
                        '   `tournament_id`, `type`, `options`'
                        ') VALUES (?, ?, ?)',
                        (tournament_id, old_id, json.dumps(options)),
                    )
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `criteria`')
