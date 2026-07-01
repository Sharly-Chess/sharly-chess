from database.sqlite.migration import BaseMigration


# Screen types seeded as default menus in every event, each grouping all
# screens of that type. They carry no stored name: their display name is
# derived from the (translatable) screen type label until an admin renames
# them. Editable and deletable like any other menu.
_DEFAULT_MENU_SCREEN_TYPES: list[str] = [
    'input',
    'check-in',
    'boards',
    'players',
    'ranking',
    'results',
]


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'CREATE TABLE `menu` ('
            '   `id` INTEGER NOT NULL,'
            '   `name` TEXT,'
            '   `default_type` TEXT,'
            '   PRIMARY KEY(`id` AUTOINCREMENT)'
            ')'
        )
        self.database.execute(
            'CREATE TABLE `menu_item` ('
            '   `id` INTEGER NOT NULL,'
            '   `menu_id` INTEGER NOT NULL,'
            '   `screen_id` INTEGER,'
            '   `family_id` INTEGER,'
            '   `screen_type` TEXT,'
            '   `index` INTEGER NOT NULL DEFAULT 0,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`menu_id`) REFERENCES '
            '   `menu`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`screen_id`) REFERENCES '
            '   `screen`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`family_id`) REFERENCES '
            '   `family`(`id`) ON DELETE CASCADE'
            ')'
        )
        for screen_type in _DEFAULT_MENU_SCREEN_TYPES:
            self.database.execute(
                'INSERT INTO `menu` (`name`, `default_type`) VALUES (NULL, ?)',
                (screen_type,),
            )
            self.database.execute('SELECT last_insert_rowid() AS `id`')
            menu_id = self.database.fetchone()['id']
            self.database.execute(
                'INSERT INTO `menu_item` '
                '(`menu_id`, `screen_type`, `index`) VALUES (?, ?, 0)',
                (menu_id, screen_type),
            )

        # Drop the legacy per-screen/family menu configuration (`menu_link`
        # and the `menu` DSL): navigation is now driven by these global menus.
        # The per-entity label survives in `menu_text`.
        self.database.execute('ALTER TABLE `screen` DROP COLUMN `menu_link`')
        self.database.execute('ALTER TABLE `screen` DROP COLUMN `menu`')
        self.database.execute('ALTER TABLE `family` DROP COLUMN `menu_link`')
        self.database.execute('ALTER TABLE `family` DROP COLUMN `menu`')

    def backward(self):
        self.database.execute('ALTER TABLE `screen` ADD `menu_link` INTEGER')
        self.database.execute('ALTER TABLE `screen` ADD `menu` TEXT')
        self.database.execute(
            'ALTER TABLE `family` ADD `menu_link` INTEGER NOT NULL DEFAULT 0'
        )
        self.database.execute(
            "ALTER TABLE `family` ADD `menu` TEXT NOT NULL DEFAULT ''"
        )
        self.database.execute('DROP TABLE `menu_item`')
        self.database.execute('DROP TABLE `menu`')
