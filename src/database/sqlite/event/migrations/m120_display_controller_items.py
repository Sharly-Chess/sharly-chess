from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """What is designed for a display controller, and what else it can show;
    which screens accept input; and whether the screens show fake data.

    A screen, multi-screen, rotator or menu may be designed for any number of
    controllers, and a controller for any number of them. What a controller is
    showing stays in its own columns, now including a multi-screen, held on one
    of its pages (counted from 1) or going through them all, or a menu.

    A screen or multi-screen accepts input or not: results on the pairings
    screens, check-ins on the check-in screens. The results entry type gives way
    to the pairings by board type with input accepted, and every check-in
    screen, interactive until now, accepts it.

    The event says whether its screens show made-up data for the tournaments
    that have not started, while they are being set up, and a multi-screen may
    set how long each of its pages is shown wherever they turn.

    A ranking screen or multi-screen may hide some of its columns, kept as a
    JSON list of their toggle ids; existing ones show all their columns. A
    round-robin grid screen orders its members by pairing number, or by rank,
    and a team one may show a row per player rather than per team. A team
    check-in screen or multi-screen may list the members of each team.
    """

    ITEM_COLUMNS = ('screen', 'family', 'rotator', 'menu')

    def forward(self) -> None:
        self.database.execute(
            'CREATE TABLE `display_controller_item` ('
            '   `id` INTEGER NOT NULL,'
            '   `display_controller_id` INTEGER NOT NULL,'
            '   `screen_id` INTEGER,'
            '   `family_id` INTEGER,'
            '   `rotator_id` INTEGER,'
            '   `menu_id` INTEGER,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`display_controller_id`) REFERENCES '
            '   `display_controller`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`screen_id`) REFERENCES '
            '   `screen`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`family_id`) REFERENCES '
            '   `family`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`rotator_id`) REFERENCES '
            '   `rotator`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`menu_id`) REFERENCES '
            '   `menu`(`id`) ON DELETE CASCADE'
            ')'
        )
        for item in self.ITEM_COLUMNS:
            self.database.execute(
                f'CREATE UNIQUE INDEX `display_controller_item_{item}` '
                f'ON `display_controller_item`(`display_controller_id`, `{item}_id`) '
                f'WHERE `{item}_id` IS NOT NULL'
            )
        self.database.execute(
            'ALTER TABLE `display_controller` ADD `family_id` INTEGER '
            'REFERENCES `family`(`id`) ON DELETE SET NULL'
        )
        self.database.execute(
            'ALTER TABLE `display_controller` ADD `family_page` INTEGER'
        )
        self.database.execute(
            'ALTER TABLE `display_controller` ADD `menu_id` INTEGER '
            'REFERENCES `menu`(`id`) ON DELETE SET NULL'
        )
        for table in ('screen', 'family'):
            self.database.execute(
                f'ALTER TABLE `{table}` ADD `accepts_input` INTEGER NOT NULL DEFAULT 0'
            )
            self.database.execute(
                f'UPDATE `{table}` SET `accepts_input` = 1 '
                f"WHERE `type` IN ('input', 'check-in')"
            )
            self.database.execute(
                f"UPDATE `{table}` SET `type` = 'boards' WHERE `type` = 'input'"
            )
        self.database.execute(
            "UPDATE `menu_item` SET `screen_type` = 'boards' "
            "WHERE `screen_type` = 'input'"
        )
        self.database.execute(
            "UPDATE `menu` SET `default_type` = 'boards' WHERE `default_type` = 'input'"
        )
        self.database.execute(
            'ALTER TABLE `info` ADD `screens_fake_data` INTEGER NOT NULL DEFAULT 0'
        )
        self.database.execute('ALTER TABLE `family` ADD `page_delay` INTEGER')
        for table in ('screen', 'family'):
            self.database.execute(
                f'ALTER TABLE `{table}` ADD `ranking_hidden_columns` TEXT'
            )
        for column in ('round_robin_grid_by_rank', 'round_robin_grid_players'):
            self.database.execute(
                f'ALTER TABLE `screen` ADD `{column}` INTEGER NOT NULL DEFAULT 0'
            )
        for table in ('screen', 'family'):
            self.database.execute(
                f'ALTER TABLE `{table}` '
                'ADD `check_in_show_members` INTEGER NOT NULL DEFAULT 0'
            )

    def backward(self) -> None:
        for table in ('family', 'screen'):
            self.database.execute(
                f'ALTER TABLE `{table}` DROP COLUMN `check_in_show_members`'
            )
        for column in ('round_robin_grid_players', 'round_robin_grid_by_rank'):
            self.database.execute(f'ALTER TABLE `screen` DROP COLUMN `{column}`')
        for table in ('family', 'screen'):
            self.database.execute(
                f'ALTER TABLE `{table}` DROP COLUMN `ranking_hidden_columns`'
            )
        self.database.execute('ALTER TABLE `family` DROP COLUMN `page_delay`')
        self.database.execute('ALTER TABLE `info` DROP COLUMN `screens_fake_data`')
        for table in ('screen', 'family'):
            self.database.execute(
                f"UPDATE `{table}` SET `type` = 'input' "
                f"WHERE `type` = 'boards' AND `accepts_input` = 1"
            )
            self.database.execute(f'ALTER TABLE `{table}` DROP COLUMN `accepts_input`')
        for column in ('menu_id', 'family_page', 'family_id'):
            self.database.execute(
                f'ALTER TABLE `display_controller` DROP COLUMN `{column}`'
            )
        self.database.execute('DROP TABLE `display_controller_item`')
