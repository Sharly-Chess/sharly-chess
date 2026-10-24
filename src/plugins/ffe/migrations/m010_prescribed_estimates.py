import json

from database.sqlite.migration import BaseMigration
from plugins.ffe import PLUGIN_NAME


class Migration(BaseMigration):
    """The estimates the FFE list and Papi files gave the players they do
    not rate became values typed by the arbiter, which then outranked the
    FFE estimate by age. Those estimates end in 99 below the FIDE floor
    of 1400; in the events of the plugin such a value is dropped, so that
    the player is ranked on the FFE estimate again."""

    def forward(self) -> None:
        self.database.execute('SELECT `enabled_plugins` FROM `info`')
        info = self.database.fetchone()
        if not info or PLUGIN_NAME not in json.loads(info['enabled_plugins'] or '[]'):
            return
        for table in ('player', 'player_period'):
            self.database.execute(f'SELECT `id`, `ratings` FROM `{table}`')
            for row in self.database.fetchall():
                ratings = json.loads(row['ratings'] or '{}')
                changed = False
                for rating in ratings.values():
                    if self._is_estimate(rating.get('manual')):
                        del rating['manual']
                        changed = True
                if changed:
                    self.database.execute(
                        f'UPDATE `{table}` SET `ratings` = ? WHERE `id` = ?',
                        (json.dumps(ratings), row['id']),
                    )

    def backward(self) -> None:
        pass

    @staticmethod
    def _is_estimate(value: int | None) -> bool:
        return value is not None and value < 1400 and value % 100 == 99
