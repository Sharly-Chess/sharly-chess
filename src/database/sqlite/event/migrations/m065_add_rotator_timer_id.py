from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    @staticmethod
    def are_foreign_keys_enabled() -> bool:
        return False

    def forward(self):
        # Screen: missing `ON DELETE SET NULL` constraint on the timer FK
        self.database.execute(
            """
            CREATE TABLE `screen_copy` (
                `id` INTEGER NOT NULL,
                `uniq_id` TEXT NOT NULL,
                `name` TEXT,
                `type` TEXT NOT NULL,
                `public` INTEGER,
                `columns` INTEGER,
                `menu_link` INTEGER,
                `menu_text` TEXT,
                `menu` TEXT,
                `timer_id` INTEGER,
                `players_show_unpaired` INTEGER,
                `results_limit` INTEGER,
                `results_tournament_ids` TEXT,
                `background_image` TEXT,
                `background_color` TEXT,
                `last_update` FLOAT NOT NULL,
                `results_max_age` INTEGER,
                `input_exit_button` INTEGER,
                `message_default` INTEGER NOT NULL DEFAULT 1,
                `message_text` TEXT,
                `ranking_crosstable` INTEGER,
                `ranking_round` INTEGER,
                `ranking_min_points` FLOAT,
                `ranking_max_points` FLOAT,
                `font_size` INTEGER,
                `players_show_opponent` INTEGER,
                PRIMARY KEY(`id` AUTOINCREMENT),
                UNIQUE(`uniq_id`),
                FOREIGN KEY (`timer_id`) REFERENCES `timer`(`id`) ON DELETE SET NULL
            )
            """
        )
        self.database.execute('INSERT INTO `screen_copy` SELECT * FROM `screen`')
        self.database.execute('DROP TRIGGER delete_screen_trigger')
        self.database.execute('DROP TABLE `screen`')
        self.database.execute('ALTER TABLE `screen_copy` RENAME TO `screen`')
        self.database.execute(
            """
            CREATE TRIGGER delete_screen_trigger
            AFTER DELETE ON screen_set
            FOR EACH ROW
            BEGIN
                DELETE FROM screen WHERE
                screen.id = OLD.screen_id
                AND (
                    SELECT COUNT(*) FROM screen_set
                    WHERE screen_set.screen_id = screen.id
                ) = 0;
            END
            """
        )

        # Family: missing `ON DELETE SET NULL` constraint on the timer FK
        self.database.execute(
            """
            CREATE TABLE `family_copy` (
                `id` INTEGER NOT NULL,
                `uniq_id` TEXT NOT NULL,
                `type` TEXT NOT NULL,
                `public` INTEGER,
                `name` TEXT,
                `players_show_unpaired` INTEGER,
                `columns` INTEGER,
                `menu_link` INTEGER NOT NULL,
                `menu_text` TEXT NOT NULL,
                `menu` TEXT NOT NULL,
                `timer_id` INTEGER,
                `tournament_id` INTEGER NOT NULL,
                `range` TEXT,
                `first` INTEGER,
                `last` INTEGER,
                `parts` INTEGER,
                `number` INTEGER,
                `last_update` FLOAT NOT NULL,
                `input_exit_button` INTEGER,
                `message_default` INTEGER NOT NULL DEFAULT 1,
                `message_text` TEXT,
                `ranking_crosstable` INTEGER,
                `ranking_round` INTEGER,
                `ranking_min_points` FLOAT,
                `ranking_max_points` FLOAT,
                `font_size` INTEGER,
                `players_show_opponent` INTEGER,
                PRIMARY KEY(`id` AUTOINCREMENT),
                UNIQUE(`uniq_id`),
                FOREIGN KEY (`timer_id`) REFERENCES `timer`(`id`) ON DELETE SET NULL,
                FOREIGN KEY (`tournament_id`) REFERENCES "tournament"(`id`) ON DELETE CASCADE
            )
            """
        )
        self.database.execute('INSERT INTO `family_copy` SELECT * FROM `family`')
        self.database.execute('DROP TABLE `family`')
        self.database.execute('ALTER TABLE `family_copy` RENAME TO `family`')

        # Rotator: add a timer_id column with a FK constraint
        self.database.execute(
            """
            CREATE TABLE `rotator_copy` (
                `id` INTEGER NOT NULL,
                "name" TEXT NOT NULL,
                `public` INTEGER,
                `delay` INTEGER,
                `message_default` INTEGER NOT NULL DEFAULT 1,
                `message_text` TEXT,
                `timer_id` INTEGER,
                PRIMARY KEY(`id` AUTOINCREMENT),
                UNIQUE("name"),
                FOREIGN KEY (`timer_id`) REFERENCES `timer`(`id`) ON DELETE SET NULL
            )
            """
        )
        self.database.execute(
            'INSERT INTO `rotator_copy`('
            '   `id`, `name`, `public`, `delay`, `message_default`, `message_text`'
            ') SELECT * FROM `rotator`'
        )
        self.database.execute('DROP TABLE `rotator`')
        self.database.execute('ALTER TABLE `rotator_copy` RENAME TO `rotator`')

    def backward(self):
        self.database.execute(
            """
            CREATE TABLE `rotator_copy` (
                `id` INTEGER NOT NULL,
                "name" TEXT NOT NULL,
                `public` INTEGER,
                `delay` INTEGER,
                `message_default` INTEGER NOT NULL DEFAULT 1,
                `message_text` TEXT,
                PRIMARY KEY(`id` AUTOINCREMENT),
                UNIQUE("name")
            )
            """
        )
        self.database.execute(
            'INSERT INTO `rotator_copy`('
            '   `id`, `name`, `public`, `delay`, `message_default`, `message_text`'
            ') SELECT * FROM `rotator`'
        )
        self.database.execute('DROP TABLE `rotator`')
        self.database.execute('ALTER TABLE `rotator_copy` RENAME TO `rotator`')
