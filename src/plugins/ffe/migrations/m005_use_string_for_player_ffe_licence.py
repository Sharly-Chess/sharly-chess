from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    LICENCE_MAPPING: dict[int, str] = {
        0: '',
        1: 'N',
        2: 'A',
        3: 'B',
    }

    def forward(self):
        for int_value, str_value in self.LICENCE_MAPPING.items():
            self.database.execute(
                "UPDATE `player` SET plugin_data = JSON_SET(plugin_data, '$.ffe.ffe_licence', ?) "
                "WHERE JSON_EXTRACT(plugin_data, '$.ffe.ffe_licence') = ?;",
                (str_value, int_value),
            )
        # No tournament / prize criteria renaming because the tournament_criterion
        # has been deleted and the value has been removed from the prizes

    def backward(self):
        for int_value, str_value in self.LICENCE_MAPPING.items():
            self.database.execute(
                "UPDATE `player` SET plugin_data = JSON_SET(plugin_data, '$.ffe.ffe_licence', ?) "
                "WHERE JSON_EXTRACT(plugin_data, '$.ffe.ffe_licence') = ?;",
                (int_value, str_value),
            )
