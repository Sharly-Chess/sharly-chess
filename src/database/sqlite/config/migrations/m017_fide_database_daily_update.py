from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Updates the FIDE database daily instead of on the 1st of the month.

    The list is only published monthly, but the copy has to stay within a
    day of the one the server offers, so the daily update asks the server
    what it holds and only rebuilds when that is newer.

    The delay and the action are stored as soon as the database is first
    opened, so the new default alone would only reach a new installation.
    A choice the user made is left alone, which the previous default
    identifies.
    """

    def forward(self) -> None:
        self.database.execute(
            'UPDATE `local_source_database` '
            "SET `outdate_delay` = 'daily', `outdate_action` = 'auto_update' "
            "WHERE `name` = 'fide' "
            "AND `outdate_delay` = 'month_1st' AND `outdate_action` = 'notif'"
        )

    def backward(self) -> None:
        self.database.execute(
            'UPDATE `local_source_database` '
            "SET `outdate_delay` = 'month_1st', `outdate_action` = 'notif' "
            "WHERE `name` = 'fide' "
            "AND `outdate_delay` = 'daily' AND `outdate_action` = 'auto_update'"
        )
