from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Deletes a tournament's teams along with it.

    ``team.tournament_id`` was ``ON DELETE SET NULL``, so deleting a
    tournament left its teams behind, attached to nothing and reachable
    from no tournament. Cascade instead.

    A NULL ``tournament_id`` remains a valid state: teams are created
    before being assigned to a tournament, and moving one between
    tournaments is just an update of the column — neither is affected by
    the delete rule, which only fires when the parent row goes.
    """

    # The table is rebuilt, so the ON DELETE rules of the tables pointing
    # at `team` must not fire while it is dropped.
    @staticmethod
    def are_foreign_keys_enabled() -> bool:
        return False

    def forward(self):
        self._rebuild_team_table('ON DELETE CASCADE')

    def backward(self):
        self._rebuild_team_table('ON DELETE SET NULL')

    def _rebuild_team_table(self, tournament_delete_rule: str):
        self.database.execute(
            'CREATE TABLE `team_new` ('
            '   `id` INTEGER NOT NULL,'
            '   `tournament_id` INTEGER,'
            '   `name` TEXT NOT NULL,'
            '   `pairing_number` INTEGER,'
            '   `captain_id` INTEGER,'
            '   `captain_name` TEXT,'
            '   `group_id` INTEGER,'
            '   `federation` TEXT,'
            '   `check_in` INTEGER NOT NULL DEFAULT 0,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`tournament_id`) REFERENCES '
            f'   `tournament`(`id`) {tournament_delete_rule},'
            '   FOREIGN KEY (`captain_id`) REFERENCES '
            '   `player`(`id`) ON DELETE SET NULL,'
            '   FOREIGN KEY (`group_id`) REFERENCES '
            '   `team_group`(`id`) ON DELETE SET NULL'
            ')'
        )
        self.database.execute(
            'INSERT INTO `team_new` '
            '(`id`, `tournament_id`, `name`, `pairing_number`, `captain_id`, '
            '`captain_name`, `group_id`, `federation`, `check_in`) '
            'SELECT `id`, `tournament_id`, `name`, `pairing_number`, `captain_id`, '
            '`captain_name`, `group_id`, `federation`, `check_in` FROM `team`'
        )
        self.database.execute('DROP TABLE `team`')
        self.database.execute('ALTER TABLE `team_new` RENAME TO `team`')
