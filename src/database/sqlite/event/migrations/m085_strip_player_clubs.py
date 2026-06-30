from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'UPDATE player set club = TRIM(club) WHERE club IS NOT NULL'
        )

    def backward(self):
        pass
