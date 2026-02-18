from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    TITLE_MAPPING: dict[int, str] = {
        0: '',
        10: 'AS',
        20: 'AFJ',
        30: 'AFC',
        40: 'AFO1',
        41: 'AFO2',
        50: 'AFE1',
        51: 'AFE2',
    }

    def forward(self):
        for int_value, str_value in self.TITLE_MAPPING.items():
            self.database.execute(
                "UPDATE `account` SET plugin_data = JSON_SET(plugin_data, '$.ffe.ffe_arbiter_title', ?) "
                "WHERE JSON_EXTRACT(plugin_data, '$.ffe.ffe_arbiter_title') = ?;",
                (str_value, int_value),
            )

    def backward(self):
        for int_value, str_value in self.TITLE_MAPPING.items():
            self.database.execute(
                "UPDATE `account` SET plugin_data = JSON_SET(plugin_data, '$.ffe.ffe_arbiter_title', ?) "
                "WHERE JSON_EXTRACT(plugin_data, '$.ffe.ffe_arbiter_title') = ?;",
                (int_value, str_value),
            )
