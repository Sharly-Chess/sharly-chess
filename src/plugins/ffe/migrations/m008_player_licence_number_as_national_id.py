from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """The FFE licence number of the players becomes their national id,
    sourced from the FFE, and leaves the plugin data (the FFE id stays
    there: it only keys the profile page)."""

    def forward(self) -> None:
        self.database.execute(
            'UPDATE `player` SET '
            "`national_id` = JSON_EXTRACT(`plugin_data`, '$.ffe.ffe_licence_number'), "
            "`national_source` = 'ffe' "
            "WHERE JSON_EXTRACT(`plugin_data`, '$.ffe.ffe_licence_number') IS NOT NULL "
            'AND `national_id` IS NULL'
        )
        self.database.execute(
            'UPDATE `player` SET '
            "`plugin_data` = JSON_REMOVE(`plugin_data`, '$.ffe.ffe_licence_number') "
            "WHERE JSON_EXTRACT(`plugin_data`, '$.ffe.ffe_licence_number') IS NOT NULL"
        )

    def backward(self) -> None:
        self.database.execute(
            'UPDATE `player` SET `plugin_data` = JSON_SET('
            "COALESCE(`plugin_data`, '{}'), '$.ffe.ffe_licence_number', `national_id`"
            ") WHERE `national_source` = 'ffe' AND `national_id` IS NOT NULL"
        )
        self.database.execute(
            'UPDATE `player` SET `national_id` = NULL, `national_source` = NULL '
            "WHERE `national_source` = 'ffe'"
        )
