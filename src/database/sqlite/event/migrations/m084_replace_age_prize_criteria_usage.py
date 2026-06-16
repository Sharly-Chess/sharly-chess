import json

from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'SELECT `id`, `options` FROM `prize_criterion` WHERE `type` = ?',
            ('AGE',),
        )
        for row in self.database.fetchall():
            options = json.loads(row['options'])
            categories = sorted(
                options.get('AGE_CATEGORIES', []),
                key=lambda cat: (
                    cat.startswith('O'),
                    int(cat[1:]),
                ),
            )
            min_category = categories[0]
            max_category = categories[-1]
            if options.get('AGE_LOWER'):
                min_category = None
            elif options.get('AGE_GREATER'):
                max_category = None
            new_options = {
                'MIN_AGE_CATEGORY': min_category,
                'MAX_AGE_CATEGORY': max_category,
            }
            self.database.execute(
                'UPDATE `prize_criterion` SET `options` = ? WHERE `id` = ?;',
                (json.dumps(new_options), row['id']),
            )

    def backward(self):
        self.database.execute(
            'SELECT `id`, `options` FROM `prize_criterion` WHERE `type` = ?',
            ('AGE',),
        )

        for row in self.database.fetchall():
            options = json.loads(row['options'])
            min_category = options.get('MIN_AGE_CATEGORY')
            max_category = options.get('MAX_AGE_CATEGORY')

            new_options = {
                'AGE_CATEGORIES': (
                    [min_category, max_category]
                    if min_category and max_category
                    else [min_category or max_category]
                ),
                'AGE_LOWER': not bool(min_category),
                'AGE_GREATER': not bool(max_category),
            }
            self.database.execute(
                'UPDATE `prize_criterion` SET `options` = ? WHERE `id` = ?;',
                (json.dumps(new_options), row['id']),
            )
