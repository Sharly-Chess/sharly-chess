from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Says which screens may be reached from outside the venue.

    Separate from `public`, which decides *who* may look: a public screen still
    asks nothing of whoever opens it, and a private one still asks them to log
    in, over the internet exactly as on the local network. This decides
    something else — whether the screen leaves the building at all.

    The two are wanted independently. A public input screen should stay on the
    venue network, where being in the room is what stands between a player and
    somebody else's result; a pairing display alongside it is worth showing to
    anyone following the tournament.

    Off for everything, including screens that already exist. A screen's type
    can be changed after the fact, so a display screen that had been left
    reachable would carry that across on the day it became an input screen, and
    nobody would be told.
    """

    TABLES = ('screen', 'family', 'rotator', 'display_controller')

    def forward(self):
        for table in self.TABLES:
            self.database.execute(
                f'ALTER TABLE `{table}` ADD `remote` INTEGER NOT NULL DEFAULT 0'
            )

    def backward(self):
        for table in self.TABLES:
            self.database.execute(f'ALTER TABLE `{table}` DROP COLUMN `remote`')
