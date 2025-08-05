from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            """
            UPDATE tournament
            SET tie_breaks = REPLACE(tie_breaks, 'SONNENBORN_BERGER', 'SONNEBORN_BERGER')
            """
        )

    def backward(self):
        self.database.execute(
            """
            UPDATE tournament
            SET tie_breaks = REPLACE(tie_breaks, 'SONNEBORN_BERGER', 'SONNENBORN_BERGER')
            """
        )
