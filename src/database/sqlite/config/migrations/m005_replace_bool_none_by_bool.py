from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        default_fields = {
            'launch_browser': True,
            'console_color': True,
            'console_show_date': False,
            'console_show_level': False,
            'experimental': False,
        }
        field_sets = [
            f'`{field}` = COALESCE(`{field}`, ?)' for field in default_fields.keys()
        ]
        self.database.execute(
            f'UPDATE `info` SET {", ".join(field_sets)}', tuple(default_fields.values())
        )

    def backward(self):
        pass
