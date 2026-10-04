import json
from typing import ClassVar

from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Each rating of a sequence names its kind besides its list and its
    cadence: ``fide:<cadence>`` the FIDE list, ``national:f:<cadence>``
    the FIDE rating a national list gives and ``national:n:<cadence>``
    its national rating. A list of a sequence gave the kinds of the
    rating preference in turn, which the sequence now spells out, the
    FIDE ratings of the FIDE list first. A rating the arbiter chose is
    keyed the same way."""

    #: The kinds of rating each preference tried, in order.
    _KINDS: ClassVar[dict[int, str]] = {
        1: 'f',
        2: 'n',
        3: 'fn',
        4: 'nf',
        5: 'fn',
        6: 'fn',
    }

    def forward(self) -> None:
        self.database.execute('SELECT `rating_preference` FROM `info`')
        info = self.database.fetchone()
        event_preference = info['rating_preference'] if info else None
        self.database.execute(
            'SELECT `id`, `rating_preference`, `rating_sequence` FROM `tournament`'
        )
        for row in self.database.fetchall():
            lists = json.loads(row['rating_sequence'] or '[]')
            if not lists:
                continue
            preference = row['rating_preference'] or event_preference or 1
            entries: list[str] = []
            for kind in self._KINDS[preference]:
                if kind == 'f':
                    entries += [key for key in lists if key.startswith('fide:')]
                entries += [
                    f'national:{kind}:{key.split(":")[1]}'
                    for key in lists
                    if key.startswith('national:')
                ]
            self.database.execute(
                'UPDATE `tournament` SET `rating_sequence` = ? WHERE `id` = ?',
                (json.dumps(list(dict.fromkeys(entries))), row['id']),
            )
        self._rename_pins(
            {'f:fide': 'fide', 'f:national': 'national:f', 'n:national': 'national:n'}
        )

    def backward(self) -> None:
        self.database.execute('SELECT `id`, `rating_sequence` FROM `tournament`')
        for row in self.database.fetchall():
            entries = json.loads(row['rating_sequence'] or '[]')
            lists = [f'{key.split(":")[0]}:{key.split(":")[-1]}' for key in entries]
            self.database.execute(
                'UPDATE `tournament` SET `rating_sequence` = ? WHERE `id` = ?',
                (json.dumps(list(dict.fromkeys(lists))), row['id']),
            )
        self._rename_pins(
            {'fide': 'f:fide', 'national:f': 'f:national', 'national:n': 'n:national'}
        )

    def _rename_pins(self, prefixes: dict[str, str]) -> None:
        for table in ('player', 'player_period'):
            self.database.execute(f'SELECT `id`, `ratings` FROM `{table}`')
            for row in self.database.fetchall():
                ratings = json.loads(row['ratings'] or '{}')
                changed = False
                for rating in ratings.values():
                    if pinned := rating.get('pinned'):
                        prefix, cadence = pinned.rsplit(':', 1)
                        if prefix in prefixes:
                            rating['pinned'] = f'{prefixes[prefix]}:{cadence}'
                            changed = True
                if changed:
                    self.database.execute(
                        f'UPDATE `{table}` SET `ratings` = ? WHERE `id` = ?',
                        (json.dumps(ratings), row['id']),
                    )
