from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'CREATE TABLE `player` ('
            '   `id` INTEGER NOT NULL,'
            '   `last_name` TEXT NOT NULL,'
            '   `first_name` TEXT,'
            '   `date_of_birth` TEXT,'
            '   `gender` INTEGER NOT NULL,'
            '   `mail` TEXT,'
            '   `phone` TEXT,'
            '   `comment` TEXT,'
            '   `owed` FLOAT NOT NULL,'
            '   `paid` FLOAT NOT NULL,'
            '   `title` INTEGER NOT NULL,'
            '   `ratings` TEXT NOT NULL,'
            '   `fide_id` INTEGER,'
            '   `federation` TEXT,'
            '   `club` TEXT,'
            '   `fixed` INTEGER,'
            '   `check_in` INTEGER NOT NULL DEFAULT 0,'
            '   `plugin_data` TEXT NOT NULL,'
            '   PRIMARY KEY(`id` AUTOINCREMENT)'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `tournament_player` ('
            '   `tournament_id` INTEGER NOT NULL,'
            '   `player_id` INTEGER NOT NULL,'
            '   `pairing_number` INTEGER,'
            '   PRIMARY KEY (`tournament_id`, `player_id`),'
            '   FOREIGN KEY (`tournament_id`) REFERENCES '
            '   `tournament`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`player_id`) REFERENCES '
            '   `player`(`id`) ON DELETE CASCADE'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `board` ('
            '   `id` INTEGER NOT NULL,'
            '   `white_player_id` INTEGER NOT NULL,'
            '   `black_player_id` INTEGER,'
            '   `index` INTEGER NOT NULL,'
            '   `last_result_update` FLOAT,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`white_player_id`) REFERENCES '
            '   `player`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`black_player_id`) REFERENCES '
            '   `player`(`id`) ON DELETE CASCADE'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `pairing` ('
            '   `tournament_id` INTEGER NOT NULL,'
            '   `player_id` INTEGER NOT NULL,'
            '   `round` INTEGER NOT NULL,'
            '   `result` INTEGER NOT NULL,'
            '   `board_id` INTEGER,'
            '   PRIMARY KEY (`tournament_id`, `player_id`, `round`),'
            '   FOREIGN KEY (`tournament_id`) REFERENCES '
            '   `tournament`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`player_id`) REFERENCES '
            '   `player`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`board_id`) REFERENCES '
            '   `board`(`id`) ON DELETE CASCADE'
            ')'
        )
        self.database.execute('DROP TABLE `result`')

    def backward(self):
        self.database.execute('DROP TABLE `pairing`')
        self.database.execute('DROP TABLE `board`')
        self.database.execute('DROP TABLE `tournament_player`')
        self.database.execute('DROP TABLE `player`')

        self.database.execute(
            'CREATE TABLE `result` ('
            '    `id` INTEGER NOT NULL,'
            '    `tournament_id` INTEGER NOT NULL,'
            '    `round` INTEGER NOT NULL,'
            '    `board_id` INTEGER NOT NULL,'
            '    `white_player_id` INTEGER NOT NULL,'
            '    `black_player_id` INTEGER NOT NULL,'
            '    `date` FLOAT NOT NULL,'
            '    `value` INTEGER NOT NULL,'
            '    PRIMARY KEY(`id` AUTOINCREMENT),'
            '    FOREIGN KEY (`tournament_id`) REFERENCES `tournament`(`id`) ON DELETE CASCADE'
            ')'
        )
