import base64
import json
from collections.abc import Callable

from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def _replace_list_values(self, replace_function: Callable[[str], str]):
        for prefix in ('tournament', 'prize'):
            for filter_id in ('CLUB', 'FEDERATION'):
                option_id = f'{filter_id}S'
                self.database.execute(
                    f'SELECT `id`, `options` FROM '
                    f'`{prefix}_criterion` WHERE `type` = ?',
                    (filter_id,),
                )
                for row in self.database.fetchall():
                    options = json.loads(row['options'])
                    value_list = [
                        replace_function(item) for item in options.get(option_id, [])
                    ]
                    options[option_id] = value_list
                    self.database.execute(
                        f'UPDATE `{prefix}_criterion` SET '
                        f'`options` = ? WHERE `id` = ?;',
                        (json.dumps(options), row['id']),
                    )

    def forward(self):
        self._replace_list_values(lambda item: base64.b64decode(item).decode('utf-8'))

    def backward(self):
        self._replace_list_values(
            lambda item: base64.b64encode(item.encode('utf-8')).decode('utf-8')
        )
