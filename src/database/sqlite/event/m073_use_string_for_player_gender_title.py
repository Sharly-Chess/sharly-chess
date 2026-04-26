from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    LEGACY_TIE_BREAKS = [
        'SONNEBORN_BERGER',
        'AVERAGE_OF_BUCHHOLZ',
        'SUM_OF_BUCHHOLZ',
        'FORE_BUCHHOLZ',
        'BUCHHOLZ',
    ]

    def forward(self):
        query_list = ', '.join(['?'] * len(self.LEGACY_TIE_BREAKS))
        self.database.execute(
            'UPDATE `tie_break` SET `options` = '
            "JSON_SET(options, '$.LEGACY_03_2026', JSON('true')) "
            f'WHERE `type` IN ({query_list})',
            tuple(self.LEGACY_TIE_BREAKS),
        )

    def backward(self):
        pass
