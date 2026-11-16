from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """A timer hour is either the start of a round or a moment with a label.

    One text field used to hold both: digits meant a round, anything else a
    label, and it had to be unique within the timer. A round hour now keeps
    its number, with an optional label shown before the round ("Opens A-D"),
    and any other hour keeps its label alone. Labels no longer need to be
    unique, so the same moment can come back on another day.
    """

    # The table is rebuilt, so the ON DELETE rules of the tables it points
    # at must not fire while it is dropped.
    @staticmethod
    def are_foreign_keys_enabled() -> bool:
        return False

    def forward(self) -> None:
        self.database.execute(
            'CREATE TABLE `timer_hour_new` ('
            '   `id` INTEGER NOT NULL,'
            '   `timer_id` INTEGER NOT NULL,'
            '   `round` INTEGER,'
            '   `label` TEXT,'
            '   `triggered_at` TEXT,'
            '   `text_before` TEXT,'
            '   `text_after` TEXT,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   FOREIGN KEY (`timer_id`) REFERENCES '
            '   `timer`(`id`) ON DELETE CASCADE'
            ')'
        )
        self.database.execute(
            'SELECT `id`, `timer_id`, `uniq_id`, `triggered_at`, '
            '`text_before`, `text_after` FROM `timer_hour`'
        )
        rows = list(self.database.fetchall())
        for row in rows:
            uniq_id: str = (row['uniq_id'] or '').strip()
            round_: int | None = None
            label: str | None = None
            if uniq_id.isdigit() and int(uniq_id) > 0:
                round_ = int(uniq_id)
            else:
                label = uniq_id or None
            self.database.execute(
                'INSERT INTO `timer_hour_new` (`id`, `timer_id`, `round`, '
                '`label`, `triggered_at`, `text_before`, `text_after`) '
                'VALUES (?, ?, ?, ?, ?, ?, ?)',
                (
                    row['id'],
                    row['timer_id'],
                    round_,
                    label,
                    row['triggered_at'],
                    row['text_before'],
                    row['text_after'],
                ),
            )
        self.database.execute('DROP TABLE `timer_hour`')
        self.database.execute('ALTER TABLE `timer_hour_new` RENAME TO `timer_hour`')

    def backward(self) -> None:
        self.database.execute(
            'CREATE TABLE `timer_hour_old` ('
            '   `id` INTEGER NOT NULL,'
            '   `uniq_id` TEXT NOT NULL,'
            '   `timer_id` INTEGER NOT NULL,'
            '   `text_before` TEXT,'
            '   `text_after` TEXT,'
            '   `triggered_at` TEXT,'
            '   PRIMARY KEY(`id` AUTOINCREMENT),'
            '   UNIQUE(`timer_id`, `uniq_id`),'
            '   FOREIGN KEY (`timer_id`) REFERENCES `timer`(`id`) ON DELETE CASCADE'
            ')'
        )
        self.database.execute(
            'SELECT `id`, `timer_id`, `round`, `label`, `triggered_at`, '
            '`text_before`, `text_after` FROM `timer_hour` ORDER BY `id`'
        )
        rows = list(self.database.fetchall())
        used: set[tuple[int, str]] = set()
        for row in rows:
            base = str(row['round']) if row['round'] else row['label'] or '?'
            uniq_id = base
            suffix = 2
            while (row['timer_id'], uniq_id) in used:
                uniq_id = f'{base} ({suffix})'
                suffix += 1
            used.add((row['timer_id'], uniq_id))
            self.database.execute(
                'INSERT INTO `timer_hour_old` (`id`, `uniq_id`, `timer_id`, '
                '`text_before`, `text_after`, `triggered_at`) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (
                    row['id'],
                    uniq_id,
                    row['timer_id'],
                    row['text_before'],
                    row['text_after'],
                    row['triggered_at'],
                ),
            )
        self.database.execute('DROP TABLE `timer_hour`')
        self.database.execute('ALTER TABLE `timer_hour_old` RENAME TO `timer_hour`')
