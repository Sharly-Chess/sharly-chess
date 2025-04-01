from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        deprecated_columns = {
            'info': [
                'chessevent_user_id',
                'chessevent_password',
                'chessevent_event_id',
            ],
            'tournament': [
                'chessevent_user_id',
                'chessevent_password',
                'chessevent_event_id',
                'chessevent_tournament_name',
                'ffe_id',
                'ffe_password',
                'last_ffe_upload',
                'last_ffe_rules_upload',
                'last_chessevent_download_md5',
            ],
        }

        for table in deprecated_columns:
            for column in deprecated_columns[table]:
                self.database.execute(
                    f'ALTER TABLE `{table}` RENAME COLUMN '
                    f'`{column}` TO `deprecated_{column}`'
                )

    # No backward as reverse renaming would interfere with plugin migrations
