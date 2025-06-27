from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            """
            CREATE TRIGGER delete_screen_trigger
            AFTER DELETE ON screen_set
            FOR EACH ROW
            BEGIN
                DELETE FROM screen WHERE
                screen.id = OLD.screen_id
                AND (
                    SELECT COUNT(*) FROM screen_set
                    WHERE screen_set.screen_id = screen.id
                ) = 0;
            END
            """
        )

    def backward(self):
        self.database.execute('DROP TRIGGER delete_screen_trigger')
