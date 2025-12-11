import json
from typing import Literal

from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    CRITERION_ID = 'AGE'
    OPTION_ID = 'AGE_CATEGORIES'

    CATEGORY_ID_BY_PREVIOUS_ID: dict[int, str] = {
        0: 'NONE',
        1: 'U8',
        2: 'U10',
        3: 'U12',
        4: 'U14',
        5: 'U16',
        6: 'U18',
        7: 'U20',
        8: 'O20',
        9: 'O50',
        10: 'O65',
    }
    CATEGORY_PREVIOUS_ID_BY_ID: dict[str, int] = {
        category_id: previous_id
        for previous_id, category_id in CATEGORY_ID_BY_PREVIOUS_ID.items()
    }

    def _rename_category_criterion(
        self,
        table: Literal['prize_criterion', 'tournament_criterion'],
        is_forward: bool,
    ):
        self.database.execute(
            f'SELECT `id`, `options` FROM `{table}` WHERE `type` = ?',
            (self.CRITERION_ID,),
        )
        for row in self.database.fetchall():
            options = json.loads(row['options'] or '{}')
            if self.OPTION_ID not in options:
                continue
            option_values: list[int | str] = []
            for value in options[self.OPTION_ID]:
                if is_forward:
                    option_values.append(self.CATEGORY_ID_BY_PREVIOUS_ID[value])
                else:
                    option_values.append(self.CATEGORY_PREVIOUS_ID_BY_ID[value])
            options[self.OPTION_ID] = option_values
            self.database.execute(
                f'UPDATE `{table}` SET `options` = ? WHERE `id` = ?',
                (json.dumps(options), row['id']),
            )

    def forward(self):
        self.database.execute('ALTER TABLE `info` ADD `age_categories` TEXT')
        self._rename_category_criterion('tournament_criterion', is_forward=True)
        self._rename_category_criterion('prize_criterion', is_forward=True)

    def backward(self):
        self.database.execute('ALTER TABLE `info` DROP COLUMN `age_categories`')
        self._rename_category_criterion('tournament_criterion', is_forward=False)
        self._rename_category_criterion('prize_criterion', is_forward=False)
