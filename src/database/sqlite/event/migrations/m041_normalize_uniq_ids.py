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
                index += 1
                new_uniq_id = f'{uniq_id}-{index}'
            suffixed_uniq_id_by_id[id_] = new_uniq_id
        return suffixed_uniq_id_by_id

    def _sanitize_table_uniq_ids(self, table_name: str):
        """Sanitize all the uniq_id fields of a table.
        Ensures the field is uniq in the table."""
        self.database.execute(f'SELECT `id`, `uniq_id` FROM `{table_name}`')
        uniq_id_by_id = {row['id']: row['uniq_id'] for row in self.database.fetchall()}
        new_uniq_id_by_id = self._add_uniq_suffixes(
            {
                id_: self._sanitize_uniq_id(uniq_id)
                for id_, uniq_id in uniq_id_by_id.items()
            }
        )
        # Values need to be inserted in the correct order
        # to ensure the UNIQUE constraints are not violated
        values_to_insert: list[tuple[int, str]] = list(new_uniq_id_by_id.items())
        while values_to_insert:
            id_, uniq_id = values_to_insert[0]
            if uniq_id in (uniq_id_by_id | {id_: None}).values():
                values_to_insert.append((id_, uniq_id))
            else:
                if uniq_id != uniq_id_by_id[id_]:
                    self.database.execute(
                        f'UPDATE `{table_name}` SET `uniq_id` = ? WHERE `id` = ?',
                        (uniq_id, id_),
                    )
                    uniq_id_by_id[id_] = uniq_id
            values_to_insert.pop(0)

    def forward(self):
        self._sanitize_table_uniq_ids('screen')
        self._sanitize_table_uniq_ids('family')

    def backward(self):
        pass
