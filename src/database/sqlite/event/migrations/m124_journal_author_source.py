from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """The journal tells who did something apart from where it came from.

    Who is a person, known through the account they act from: the
    administrator or a staff account, or nobody, when the action comes from
    a public screen, a synchronisation or the application itself. Where is
    the computer running the application, a device of the network, a
    screen, a plugin or the application. An entry made on a screen by an
    arbiter signed in names both.

    A staff account is kept by its id alone, and shown by the name it has:
    the entry of its deletion keeps the name of an account deleted.
    """

    def forward(self) -> None:
        for column in (
            '`author_kind` TEXT',
            "`source_kind` TEXT NOT NULL DEFAULT 'application'",
            '`source_name` TEXT',
        ):
            self.database.execute(f'ALTER TABLE `journal` ADD {column}')
        self.database.execute(
            'UPDATE `journal` SET '
            "`author_kind` = CASE WHEN `actor_kind` IN ('administrator', 'account') "
            'THEN `actor_kind` END, '
            '`source_kind` = CASE '
            "WHEN `actor_kind` IN ('screen', 'plugin') THEN `actor_kind` "
            "WHEN `actor_kind` = 'system' THEN 'application' "
            "WHEN `host` IS NULL OR `host` IN ('127.0.0.1', '::1', 'localhost') "
            "THEN 'computer' ELSE 'network' END, "
            "`source_name` = CASE WHEN `actor_kind` IN ('screen', 'plugin') "
            'THEN `actor_name` END'
        )
        self.database.execute(
            'UPDATE `journal` SET `account_id` = NULL WHERE `author_kind` IS NULL'
        )
        self.database.execute('ALTER TABLE `journal` DROP COLUMN `actor_kind`')
        self.database.execute('ALTER TABLE `journal` DROP COLUMN `actor_name`')

    def backward(self) -> None:
        self.database.execute(
            "ALTER TABLE `journal` ADD `actor_kind` TEXT NOT NULL DEFAULT 'system'"
        )
        self.database.execute('ALTER TABLE `journal` ADD `actor_name` TEXT')
        self.database.execute(
            'UPDATE `journal` SET '
            '`actor_kind` = CASE '
            'WHEN `author_kind` IS NOT NULL THEN `author_kind` '
            "WHEN `source_kind` IN ('screen', 'plugin') THEN `source_kind` "
            "WHEN `source_kind` = 'network' THEN 'anonymous' "
            "ELSE 'system' END, "
            '`actor_name` = CASE WHEN `author_kind` IS NULL '
            "AND `source_kind` IN ('screen', 'plugin') THEN `source_name` END"
        )
        for column in ('source_name', 'source_kind', 'author_kind'):
            self.database.execute(f'ALTER TABLE `journal` DROP COLUMN `{column}`')
