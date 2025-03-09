from database.sqlite.config.config_migration import AbstractConfigMigration


class ConfigMigration(AbstractConfigMigration):
    def forward(self):
        self.execute(
            'CREATE TABLE `info` ('
            '    `version` TEXT NOT NULL,'
            '    `force_edit` INTEGER NOT NULL,'
            '    `log_level` INTEGER,'
            '    `launch_browser` INTEGER,'
            '    `federation` TEXT,'
            '    `locale` TEXT'
            ')'
        )
