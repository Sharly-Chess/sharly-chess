from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        # A bug that has been corrected in version 3.1.4 led to a situation where databases older than migration 10 would lose
        # all the screenset data when updated by a version of the app > 2.8 (when PRAGMA foreign_keys was turned on).
        # This leaves the database in a state where it's impossible to access the screens page.
        # We can do no better than deleting these screens to allow the application to work.
        self.database.execute(
            """
            DELETE FROM screen
            WHERE id NOT IN (
                SELECT DISTINCT screen_id FROM screen_set
            )
            """
        )

    def backward(self):
        pass
