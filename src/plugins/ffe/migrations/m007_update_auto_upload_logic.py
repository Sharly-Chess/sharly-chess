from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            "SELECT JSON_EXTRACT(plugin_data, '$.ffe.auto_upload') AS auto_upload FROM info"
        )
        event_auto_upload = bool(self.database.fetchone()['auto_upload'])
        self.database.execute(
            "UPDATE `tournament` SET plugin_data = JSON_SET(plugin_data, '$.ffe.auto_upload', ?) "
            "WHERE JSON_EXTRACT(plugin_data, '$.ffe.auto_upload') IS NULL",
            (event_auto_upload,),
        )

    def backward(self):
        pass
