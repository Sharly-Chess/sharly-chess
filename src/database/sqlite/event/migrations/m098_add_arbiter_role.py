from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Prevent an account from holding multiple arbiter roles for one tournament."""

    def forward(self):
        self.database.execute('DROP INDEX `ux_no_dual_arbiter_role`')
        self.database.execute(
            'CREATE UNIQUE INDEX `ux_no_dual_arbiter_role` '
            'ON `account_role`(`account_id`, `tournament_id`) '
            'WHERE `role` IN ("chief_arbiter", "deputy_arbiter", "arbiter")'
        )

    def backward(self):
        self.database.execute('DROP INDEX `ux_no_dual_arbiter_role`')
        self.database.execute(
            'CREATE UNIQUE INDEX `ux_no_dual_arbiter_role` '
            'ON `account_role`(`account_id`, `tournament_id`) '
            'WHERE `role` IN ("chief_arbiter", "deputy_arbiter")'
        )
