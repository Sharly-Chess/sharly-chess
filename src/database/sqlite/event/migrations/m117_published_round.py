from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    """The current round becomes the last round whose pairings are published
    to the screens and the online services.

    Every round already paired stays visible: the last paired round, or for
    a round-robin, whose rounds are all paired at once, the round the
    arbiter had made current (else the last round with a result, else the
    first round paired)."""

    def forward(self) -> None:
        self.database.execute(
            'UPDATE `tournament` SET `current_round` = CASE '
            "    WHEN `pairing` LIKE 'ROUND\\_ROBIN\\_%' ESCAPE '\\' THEN COALESCE("
            '        NULLIF(`current_round`, 0),'
            '        (SELECT MAX(`round`) FROM `pairing`'
            '         WHERE `pairing`.`tournament_id` = `tournament`.`id`'
            '         AND `board_id` IS NOT NULL AND `result` != 0),'
            '        (SELECT MIN(`round`) FROM `pairing`'
            '         WHERE `pairing`.`tournament_id` = `tournament`.`id`'
            '         AND `board_id` IS NOT NULL),'
            '        0)'
            '    ELSE MAX('
            '        COALESCE((SELECT MAX(`round`) FROM `pairing`'
            '         WHERE `pairing`.`tournament_id` = `tournament`.`id`'
            '         AND `board_id` IS NOT NULL), 0),'
            '        COALESCE((SELECT MAX(`round`) FROM `team_board`'
            '         WHERE `team_board`.`tournament_id` = `tournament`.`id`), 0))'
            'END'
        )
        self.database.execute(
            'ALTER TABLE `tournament` RENAME COLUMN `current_round` TO `published_round`'
        )

    def backward(self) -> None:
        self.database.execute(
            'ALTER TABLE `tournament` RENAME COLUMN `published_round` TO `current_round`'
        )
        self.database.execute(
            'UPDATE `tournament` SET `current_round` = NULL '
            "WHERE `pairing` NOT LIKE 'ROUND\\_ROBIN\\_%' ESCAPE '\\' "
            'OR `current_round` = 0'
        )
