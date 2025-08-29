from typing_extensions import Any

from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    @staticmethod
    def _add_uniq_suffixes(name_by_id: dict[int, str]) -> dict[int, str]:
        suffixed_name_by_id: dict[int, str] = {}
        for id_, name in name_by_id.items():
            new_name = name
            index = 1
            used_names = suffixed_name_by_id.values()
            while new_name in used_names:
                index += 1
                new_name = f'{name} ({index})'
            suffixed_name_by_id[id_] = new_name
        return suffixed_name_by_id

    def _uniquify_table_names(
        self, table_name: str, default: str = '', group_by: str | None = None
    ):
        """Make all the `name` records of a table unique.
        If `group_by` is defined, only make the names unique amongst the records
        having the same value in the `group_by` column.
        """
        columns = ['id', 'name']
        if group_by:
            columns.append(group_by)
        columns_str = ', '.join(f'`{column}`' for column in columns)
        self.database.execute(f'SELECT {columns_str} FROM `{table_name}`')
        name_by_id_by_group_value: dict[Any, dict[int, str]] = {}
        if group_by:
            for row in self.database.fetchall():
                group_value = row[group_by]
                if group_value not in name_by_id_by_group_value:
                    name_by_id_by_group_value[group_value] = {}
                name_by_id_by_group_value[group_value][row['id']] = row['name']
        else:
            name_by_id_by_group_value[None] = {
                row['id']: row['name'] or default for row in self.database.fetchall()
            }
        for name_by_id in name_by_id_by_group_value.values():
            for id_, name in self._add_uniq_suffixes(name_by_id).items():
                self.database.execute(
                    f'UPDATE `{table_name}` SET `name` = ? WHERE `id` = ?',
                    (name, id_),
                )

    def _replace_uniq_id_by_name(self, table_name: str):
        """Replaces the `uniq_id` column by the name column.
        The entries in the name column have to be unique and not NULL to respect the constraints.
        The `uniq_id` columns can't be directly dropped because of the UNIQUE constraint."""

        # Clear the uniq_id column to avoid a constraint violation
        # Happens when a name is the same as the uniq_id of another record
        self.database.execute(
            f'UPDATE `{table_name}` SET '
            "`uniq_id` = 'tmp-unused-uniq-id-' || CAST(`id` AS TEXT)"
        )
        self.database.execute(f'UPDATE `{table_name}` SET `uniq_id` = `name`')
        self.database.execute(f'ALTER TABLE `{table_name}` DROP COLUMN `name`')
        self.database.execute(
            f'ALTER TABLE `{table_name}` RENAME COLUMN `uniq_id` TO `name`'
        )

    def forward(self):
        self._uniquify_table_names('display_controller', 'Display Controller')
        self._replace_uniq_id_by_name('display_controller')
        self._uniquify_table_names('tournament')
        self._replace_uniq_id_by_name('tournament')
        self._uniquify_table_names('prize_group', group_by='tournament_id')
        self._uniquify_table_names('prize_category', group_by='prize_group_id')

        self.database.execute('ALTER TABLE `timer` RENAME COLUMN `uniq_id` TO `name`')
        self.database.execute('ALTER TABLE `rotator` RENAME COLUMN `uniq_id` TO `name`')

    def backward(self):
        self.database.execute(
            'ALTER TABLE `display_controller` RENAME COLUMN `name` TO `uniq_id`'
        )
        self.database.execute('ALTER TABLE `display_controller` ADD `name` TEXT')
        self.database.execute('UPDATE `display_controller` SET `name` = `uniq_id`')

        self.database.execute(
            'ALTER TABLE `tournament` RENAME COLUMN `name` TO `uniq_id`'
        )
        self.database.execute('ALTER TABLE `tournament` ADD `name` TEXT')
        self.database.execute('UPDATE `tournament` SET `name` = `uniq_id`')

        self.database.execute('ALTER TABLE `timer` RENAME COLUMN `name` TO `uniq_id`')
        self.database.execute('ALTER TABLE `rotator` RENAME COLUMN `name` TO `uniq_id`')
