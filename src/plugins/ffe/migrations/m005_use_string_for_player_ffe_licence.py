import json

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

        for prefix in ('tournament', 'prize'):
            self.database.execute(
                f'SELECT * FROM `{prefix}_criterion` WHERE `type` = ?',
                ('ffe-LICENCE',),
            )
            for row in self.database.fetchall():
                licences = [
                    self.LICENCE_MAPPING[int_licence]
                    for int_licence in json.loads(row['options'])['ffe-LICENCES']
                ]
                self.database.execute(
                    f'UPDATE `{prefix}_criterion` SET `options` = ? WHERE `id` = ?',
                    (json.dumps({'ffe-LICENCES': licences}), row['id']),
                )

    def backward(self):
        for int_value, str_value in self.LICENCE_MAPPING.items():
            self.database.execute(
                "UPDATE `player` SET plugin_data = JSON_SET(plugin_data, '$.ffe.ffe_licence', ?) "
                "WHERE JSON_EXTRACT(plugin_data, '$.ffe.ffe_licence') = ?;",
                (int_value, str_value),
            )
        licence_mapping = {
            licence_str: licence_int
            for licence_int, licence_str in self.LICENCE_MAPPING.items()
        }
        for prefix in ('tournament', 'prize'):
            self.database.execute(
                f'SELECT * FROM `{prefix}_criterion` WHERE `type` = ?',
                ('ffe-LICENCE',),
            )
            for row in self.database.fetchall():
                licences = [
                    licence_mapping[str_licence]
                    for str_licence in json.loads(row['options'])['ffe-LICENCES']
                ]
                self.database.execute(
                    f'UPDATE `{prefix}_criterion` SET `options` = ? WHERE `id` = ?',
                    (json.dumps({'ffe-LICENCES': licences}), row['id']),
                )
