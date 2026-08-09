from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            'CREATE TABLE `menu` ('
            '   `id` INTEGER NOT NULL,'
            '   `name` TEXT,'
            '   `default_type` TEXT,'
            "   `submenu_mode` TEXT NOT NULL DEFAULT 'automatic',"
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
