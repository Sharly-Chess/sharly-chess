from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Every board keeps the fixed table number its players had when it was
    paired, so that editing a player's fixed table no longer renumbers the
    rounds already played. The boards paired before that number was kept,
    and the boards of imported tournaments, followed their players' current
    fixed tables instead: they keep the ones they have now."""

    def forward(self) -> None:
        self.database.execute(
            'UPDATE `board` SET `fixed_number` = MAX('
            '    COALESCE((SELECT `fixed` FROM `player` WHERE `id` = `board`.`white_player_id`), 0),'
            '    COALESCE((SELECT `fixed` FROM `player` WHERE `id` = `board`.`black_player_id`), 0)'
            ') '
            'WHERE `fixed_number` IS NULL'
        )

    def backward(self) -> None:
        pass
