from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """Let pairings-by-board screens of team tournaments show the matches
    alone, without the players of each board."""

    def forward(self) -> None:
        for table in ('screen', 'family'):
            self.database.execute(
                f'ALTER TABLE `{table}` ADD `boards_hide_players` INTEGER'
            )

    def backward(self) -> None:
        for table in ('family', 'screen'):
            self.database.execute(
                f'ALTER TABLE `{table}` DROP COLUMN `boards_hide_players`'
            )
