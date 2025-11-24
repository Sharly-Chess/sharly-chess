from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'UPDATE `screen` SET `input_exit_button` = 0 '
            'WHERE `type` = ? AND `input_exit_button` IS NULL',
            ('input',),
        )
        self.database.execute(
            'UPDATE `screen` SET `players_show_unpaired` = 0 '
            'WHERE `type` = ? AND `players_show_unpaired` IS NULL',
            ('players',),
        )
        self.database.execute(
            'UPDATE `screen` SET `players_show_opponent` = 0 '
            'WHERE `type` = ? AND `players_show_opponent` IS NULL',
            ('players',),
        )

    def backward(self):
        pass
