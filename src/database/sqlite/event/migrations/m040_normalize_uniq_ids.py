import re

from text_unidecode import unidecode

from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    @staticmethod
    def _sanitize_uniq_id(uniq_id: str) -> str:
        return re.sub(r'[^a-zA-Z0-9_\-]', '_', unidecode(uniq_id))

    @staticmethod
    def _add_uniq_suffixes(uniq_id_by_id: dict[int, str]) -> dict[int, str]:
        suffixed_uniq_id_by_id: dict[int, str] = {}
        for id_, uniq_id in uniq_id_by_id.items():
            new_uniq_id = uniq_id
            index = 1
            used_uniq_ids = suffixed_uniq_id_by_id.values()
            while new_uniq_id in used_uniq_ids:
                new_uniq_id = f'{uniq_id} ({index})'
                index += 1
            suffixed_uniq_id_by_id[id_] = new_uniq_id
        return suffixed_uniq_id_by_id

    def _sanitize_table_uniq_ids(self, table_name: str):
        """Sanitize all the uniq_id fields of a table.
        Ensures the field is uniq in the table."""
        self.database.execute(f'SELECT `id`, `uniq_id` FROM `{table_name}`')
        uniq_id_by_id = self._add_uniq_suffixes(
            {
                row['id']: self._sanitize_uniq_id(row['uniq_id'])
                for row in self.database.fetchall()
            }
        )
        for id_, uniq_id in uniq_id_by_id.items():
            self.database.execute(
                f'UPDATE `{table_name}` SET `uniq_id` = ? WHERE `id` = ?',
                (uniq_id, id_),
            )

    def forward(self):
        self._sanitize_table_uniq_ids('tournament')
        self._sanitize_table_uniq_ids('screen')
        self._sanitize_table_uniq_ids('family')
        self._sanitize_table_uniq_ids('rotator')
        self._sanitize_table_uniq_ids('display_controller')
        self._sanitize_table_uniq_ids('timer')
        # timer_hour.uniq_id does not need sanitizing as it is not referred to as a unique id
        # It is indeed more of a unique name

    def backward(self):
        pass
