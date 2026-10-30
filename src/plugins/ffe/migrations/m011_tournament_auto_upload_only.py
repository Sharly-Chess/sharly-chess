from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """The automatic upload of the results is set per tournament only: the
    tournaments of an event whose automatic upload was turned off stop
    uploading automatically, and the event setting is dropped."""

    def forward(self) -> None:
        self.database.execute(
            "SELECT JSON_EXTRACT(plugin_data, '$.ffe.auto_upload') AS auto_upload FROM info"
        )
        info = self.database.fetchone()
        if not info:
            return
        if info['auto_upload'] == 0:
            self.database.execute(
                "UPDATE `tournament` SET plugin_data = JSON_SET(plugin_data, '$.ffe.auto_upload', JSON('false')) "
                "WHERE JSON_TYPE(plugin_data, '$.ffe') IS NOT NULL",
            )
        self.database.execute(
            "UPDATE `info` SET plugin_data = JSON_REMOVE(plugin_data, '$.ffe.auto_upload')"
        )

    def backward(self) -> None:
        self.database.execute(
            "UPDATE `info` SET plugin_data = JSON_SET(plugin_data, '$.ffe.auto_upload', JSON('true')) "
            "WHERE JSON_TYPE(plugin_data, '$.ffe') IS NOT NULL"
        )
