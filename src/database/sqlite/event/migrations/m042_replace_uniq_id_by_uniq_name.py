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
                new_name = f'{name} ({index})'
                index += 1
            suffixed_name_by_id[id_] = new_name
        return suffixed_name_by_id

    def _uniquify_table_names(self, table_name: str, default: str = ''):
        """Make all the `name` records of a table unique."""
        self.database.execute(f'SELECT `id`, `name`, `uniq_id` FROM `{table_name}`')
        name_by_id: dict[int, str] = {
            row['id']: row['name'] or default for row in self.database.fetchall()
        }
        for id_, name in self._add_uniq_suffixes(name_by_id).items():
            self.database.execute(
                f'UPDATE `{table_name}` SET `name` = ? WHERE `id` = ?',
                (name, id_),
            )

    def _replace_uniq_id_by_name(self, table_name: str):
        """Replaces the `uniq_id` column by the name column.
        The entries in the name column have to be unique and not NULL to respect the constraints.
        The `uniq_id` columns can't be directly dropped because of the UNIQUE constraint."""
        self.database.execute(f'UPDATE `{table_name}` SET `uniq_id` = `name`')
        self.database.execute('ALTER TABLE `display_controller` DROP COLUMN `name`')
        self.database.execute(
            'ALTER TABLE `display_controller` RENAME COLUMN `uniq_id` TO `name`'
        )

    def forward(self):
        self._uniquify_table_names('display_controller', 'Display Controller')
        self._replace_uniq_id_by_name('display_controller')

    def backward(self):
        self.database.execute('ALTER TABLE `display_controller` ADD `uniq_id` TEXT')
        self.database.execute(
            'UPDATE `display_controller` SET '
            "`uniq_id` = 'display-controller-' || CAST(`id` as TEXT)"
        )
