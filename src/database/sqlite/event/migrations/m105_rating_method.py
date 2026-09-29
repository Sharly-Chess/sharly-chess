from database.sqlite.migration import BaseMigration

# The FIDE (3) and national (2) settings fell back to the estimated rating of
# a player without the chosen one.
_FORWARD = 'CASE `rating_method` WHEN 2 THEN 7 ELSE 6 END'
_BACKWARD = 'CASE `player_rating_type` WHEN 2 THEN 2 WHEN 4 THEN 2 WHEN 7 THEN 2 WHEN 9 THEN 2 ELSE 3 END'


class Migration(BaseMigration):
    """Replace the rating type of the event and its tournaments (FIDE or
    national) by a rating method, which also states what a player without
    that rating is ranked on."""

    def forward(self) -> None:
        for table in ('info', 'tournament'):
            self.database.execute(
                f'ALTER TABLE `{table}` '
                'RENAME COLUMN `player_rating_type` TO `rating_method`'
            )
            self.database.execute(
                f'UPDATE `{table}` SET `rating_method` = {_FORWARD} '
                'WHERE `rating_method` IS NOT NULL'
            )

    def backward(self) -> None:
        for table in ('info', 'tournament'):
            self.database.execute(
                f'ALTER TABLE `{table}` '
                'RENAME COLUMN `rating_method` TO `player_rating_type`'
            )
            self.database.execute(
                f'UPDATE `{table}` SET `player_rating_type` = {_BACKWARD} '
                'WHERE `player_rating_type` IS NOT NULL'
            )
