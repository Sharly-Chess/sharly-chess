from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `tournament` RENAME TO `tournament_copy`')
        self.database.execute('ALTER TABLE `tournament_copy` RENAME TO `tournament`')

    def backward(self):
        # NOTE(Amaras): The database is in a saner state after the migration, which does not
        # change anything to the behaviour (apart from foreign keys).
        # The best thing to do is to make the backwards migration a no-op.
        # However, note that downgraded databases will not be identical
        # to databases that did not go through the migration.
        # This may cause problems if there are behaviours relying on foreign
        # keys being wrong
        pass
