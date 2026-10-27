import json

from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """The rating a tournament ranks its players on (TEC Manual 3.9.5).

    ``rating_preference`` is the kind of rating used and the one fallen
    back on, NULL taking the event's, which NULL leaves to the plugins
    and then to FIDE. ``rating_sequence`` is the ordered lists consulted,
    empty for the default of the cadence; each tournament is given the
    sequence that reproduces how its ratings were chosen until now,
    which absorbs ``override_unrated_rapid_blitz``.

    A value typed for a player no list answers for is ``manual``, the
    ``estimated`` key it replaces."""

    def forward(self) -> None:
        self.database.execute(
            'ALTER TABLE `tournament` ADD `rating_preference` INTEGER'
        )
        self.database.execute(
            "ALTER TABLE `tournament` ADD `rating_sequence` TEXT NOT NULL DEFAULT ''"
        )
        self.database.execute(
            'SELECT `id`, `rating`, `player_rating_type`, '
            '`override_unrated_rapid_blitz` FROM `tournament`'
        )
        for row in self.database.fetchall():
            cadence = row['rating']
            sequence = [f'fide:{cadence}']
            if cadence != 1 and row['override_unrated_rapid_blitz'] != 0:
                sequence.append('fide:1')
            sequence.append(f'national:{cadence}')
            self.database.execute(
                'UPDATE `tournament` SET `rating_preference` = ?, '
                '`rating_sequence` = ? WHERE `id` = ?',
                (
                    {3: 1, 2: 2}.get(row['player_rating_type']),
                    json.dumps(sequence),
                    row['id'],
                ),
            )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `player_rating_type`'
        )
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `override_unrated_rapid_blitz`'
        )

        self.database.execute('ALTER TABLE `info` ADD `rating_preference` INTEGER')
        self.database.execute(
            'UPDATE `info` SET `rating_preference` = 2 WHERE `player_rating_type` = 2'
        )
        self.database.execute('ALTER TABLE `info` DROP COLUMN `player_rating_type`')

        self._rename_rating_key('estimated', 'manual')

    def backward(self) -> None:
        self._rename_rating_key('manual', 'estimated')

        self.database.execute(
            'ALTER TABLE `info` ADD `player_rating_type` INTEGER NOT NULL DEFAULT 3'
        )
        self.database.execute(
            'UPDATE `info` SET `player_rating_type` = 2 WHERE `rating_preference` = 2'
        )
        self.database.execute('ALTER TABLE `info` DROP COLUMN `rating_preference`')

        self.database.execute(
            'ALTER TABLE `tournament` ADD `player_rating_type` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `tournament` ADD `override_unrated_rapid_blitz` INTEGER'
        )
        self.database.execute(
            'SELECT `id`, `rating_preference`, `rating_sequence` FROM `tournament`'
        )
        for row in self.database.fetchall():
            sequence = json.loads(row['rating_sequence'] or '[]')
            self.database.execute(
                'UPDATE `tournament` SET `player_rating_type` = ?, '
                '`override_unrated_rapid_blitz` = ? WHERE `id` = ?',
                (
                    {1: 3, 2: 2}.get(row['rating_preference']),
                    int(not sequence or 'fide:1' in sequence),
                    row['id'],
                ),
            )
        self.database.execute('ALTER TABLE `tournament` DROP COLUMN `rating_sequence`')
        self.database.execute(
            'ALTER TABLE `tournament` DROP COLUMN `rating_preference`'
        )

    def _rename_rating_key(self, old_key: str, new_key: str) -> None:
        for table in ('player', 'player_period'):
            self.database.execute(f'SELECT `id`, `ratings` FROM `{table}`')
            for row in self.database.fetchall():
                ratings = json.loads(row['ratings'] or '{}')
                changed = False
                for rating in ratings.values():
                    if old_key in rating:
                        rating[new_key] = rating.pop(old_key)
                        changed = True
                if changed:
                    self.database.execute(
                        f'UPDATE `{table}` SET `ratings` = ? WHERE `id` = ?',
                        (json.dumps(ratings), row['id']),
                    )
