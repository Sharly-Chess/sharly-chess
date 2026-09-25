from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Lets the data sources be activated one by one.

    NULL until the source has been activated or deactivated once, so that
    a source can still be activated automatically (a federation event is
    created, a plugin is enabled); 0 once the user has removed it, 1 once
    it has been added.
    """

    def forward(self) -> None:
        self.database.execute(
            'ALTER TABLE `local_source_database` ADD `is_active` INTEGER'
        )
        self.database.execute(
            'CREATE TABLE `online_data_source` ('
            '   `name` TEXT NOT NULL,'
            '   `is_active` INTEGER,'
            '    PRIMARY KEY(`name`)'
            ')'
        )

    def backward(self) -> None:
        self.database.execute('DROP TABLE `online_data_source`')
        self.database.execute(
            'ALTER TABLE `local_source_database` DROP COLUMN `is_active`'
        )
