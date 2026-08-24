import json

from database.sqlite.migration import BaseMigration

POINTS_TYPE = 'POINTS'


class Migration(BaseMigration):
    """Puts the points at the head of the saved tie-break sets.

    The points became a ranking criterion of their own, and every
    tournament gained one (see the event-database migration of the same
    name). A set saved before that lists only the tie-breaks that came
    after the score, so applying it to a tournament would drop the
    points from the ranking entirely. Each set gets the criterion back,
    first, unless it already carries one.
    """

    @staticmethod
    def _points_entry() -> dict[str, object]:
        return {'type': POINTS_TYPE, 'options': {}}

    def forward(self):
        self.database.execute('SELECT `id`, `stored_tie_breaks` FROM `tie_break_set`')
        for row in self.database.fetchall():
            tie_breaks = json.loads(row['stored_tie_breaks'])
            if any(entry.get('type') == POINTS_TYPE for entry in tie_breaks):
                continue
            self.database.execute(
                'UPDATE `tie_break_set` SET `stored_tie_breaks` = ? WHERE `id` = ?',
                (json.dumps([self._points_entry(), *tie_breaks]), row['id']),
            )

    def backward(self):
        self.database.execute('SELECT `id`, `stored_tie_breaks` FROM `tie_break_set`')
        for row in self.database.fetchall():
            tie_breaks = json.loads(row['stored_tie_breaks'])
            remaining = [
                entry for entry in tie_breaks if entry.get('type') != POINTS_TYPE
            ]
            if len(remaining) == len(tie_breaks):
                continue
            self.database.execute(
                'UPDATE `tie_break_set` SET `stored_tie_breaks` = ? WHERE `id` = ?',
                (json.dumps(remaining), row['id']),
            )
