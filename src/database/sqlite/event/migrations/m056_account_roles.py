from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('ALTER TABLE `account` ADD `fide_id` INTEGER')

        # Create account_role table
        self.database.execute(
            'CREATE TABLE `account_role` ('
            '   `account_id` INTEGER NOT NULL,'
            '   `tournament_id` INTEGER,'  # NULL for organisers
            '   `role` TEXT NOT NULL CHECK (`role` IN ("chief_arbiter", "deputy_arbiter", "organiser")),'
            '   FOREIGN KEY (`account_id`) REFERENCES `account`(`id`) ON DELETE CASCADE,'
            '   FOREIGN KEY (`tournament_id`) REFERENCES `tournament`(`id`) ON DELETE CASCADE,'
            '   CHECK ('
            '       (`role` = "organiser" AND `tournament_id` IS NULL) OR '
            '       (`role` IN ("chief_arbiter", "deputy_arbiter") AND `tournament_id` IS NOT NULL)'
            '   )'
            ')'
        )

        # Prevent duplicate (account, role, tournament)
        self.database.execute(
            'CREATE UNIQUE INDEX `ux_account_role_tournament` '
            'ON `account_role`(`account_id`, `role`, `tournament_id`)'
        )

        # Only one chief arbiter per tournament
        self.database.execute(
            'CREATE UNIQUE INDEX `ux_one_chief_per_tournament` '
            'ON `account_role`(`role`, `tournament_id`) WHERE `role` = "chief_arbiter"'
        )

        # Forbid same user being both chief and deputy on same tournament
        self.database.execute(
            'CREATE UNIQUE INDEX `ux_no_dual_arbiter_role` '
            'ON `account_role`(`account_id`, `tournament_id`) '
            'WHERE `role` IN ("chief_arbiter", "deputy_arbiter")'
        )

    def backward(self):
        self.database.execute('DROP INDEX IF EXISTS `ux_no_dual_arbiter_role`')
        self.database.execute('DROP INDEX IF EXISTS `ux_one_organiser_per_account`')
        self.database.execute('DROP INDEX IF EXISTS `ux_one_chief_per_tournament`')

        self.database.execute('DROP TABLE IF EXISTS `account_role`')
        self.database.execute('ALTER TABLE `account` DROP COLUMN `fide_id`')
